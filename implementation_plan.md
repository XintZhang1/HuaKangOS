# HuaKangOS 实施计划：单项实施与检查点审阅版

计划版本：`R4-20260928`。基线：R4-B1，审阅时 HEAD `f735de2`、迁移头 `h52j_assistant_work_plans`。用户最新目标优先项目实现完成度：Codex 按既定架构推进实现，集中测试后移并交 DeepSeek。108 项功能范围、原验收标准及生产边界保留，实施门禁按下述 R4 两阶段规则执行。

**当前工作**：集中测试阶段接手 Codex 未完成批次。M5.5—M5.8、M1.4 已完成实现/审阅与外部实测并登记 `implemented`，CP-12、CP-13 记 `implementation_released`。2026-09-28 完成集中测试首轮完整基线归因（38 项过时测试合同 + 2 项产品缺陷，见 PATCH-CP-00B-08）并复跑全绿：41 条命令全部执行，`baseline_pytest` **2780 passed / 0 failed / 1 skipped**（唯一 skip 仍是符号链接环境缺口），18 条脚本命令（含 5 项 Node 前端检查）全部 successful。随后完成 M6.1（Runtime 客户端 15+7）、M6.2（发送/恢复/显式停止接入持久 Run 9+7）、M6.3（真实事项侧栏与两列工作台 10+6）、M6.4（默认进入助手与人工导航保持 6+6）、M6.5（统一交接守卫与入口 13+8）、M6.6（持续跟进与生命周期控制 12+7）、M6.7（通知/协作/回执核对 11+9）、M6.8（兼容/窄屏/开关收口 21 条命令），三者均 passed，CP-14 记 `implementation_released`。下一步 M6.4（默认进入助手并保持原人工导航与深链接）。四个功能开关默认关闭。

## R4：先完成实现，再集中测试（最高执行优先级）

2026-09-28 用户将目标更新为：“按照你的计划，直接进行实施，不再依赖deepseek或者astra low。请注意我们首要目标是项目完成度，测试阶段可以整体向后挪，后续我将统一交给deepseek完成”。本节取代本文、AGENTS 与旧交接中的逐项先测通过、先扩 runner、测试条件不满足即阻止编码等执行要求；不改变下面的产品架构、业务规则或最终验收标准。用户随后明确“批准，后续授权不用再问我，都默认允许”：PATCH-M4-5-02 与后续完成既定架构必需的文件范围补齐已获持续授权，先登记精确范围、原因、异常路径并审阅，不再重复询问；这不启动后移的测试阶段或生产部署。

1. Codex 当前阶段逐项阅读、实现、检查实际差异及必要静态合同，记录代码产物和待测范围后继续。不要为本阶段新增/运行测试套件、扩建 runner 或进行真实模型/浏览器/PostgreSQL/故障演练；这些统一移交 DeepSeek。
2. 状态新增 `implemented`：实现产物完成，集中测试未完成；`done` 仍表示原完整验收成立。编码依赖中的 `done` 暂按 `implemented` 或 `done` 判定，不伪造 passed，不把代码完成写成已验收。
3. 检查点新增 `implementation_released`：仅经代码/差异审阅允许后续实现，不能表示测试、业务或生产验收通过。原 `released` 含义和既有真实通过证据保留。测试失败/跳过、未具备的测试工具链和真实验收条件移交集中阶段，不再阻塞当前编码；实际架构冲突、无法实现的业务合同仍须解决或报告。
4. 原各项测试命令、验收条件与未勾选项全部保留，作为后续 DeepSeek 清单，不机械改为通过。纯测试、演练和试用项保持 `todo` 并注明验证移交，不挡后续尚需实现的代码、文档或交接产物；源码集成缺口仍由 Codex 完成。
5. 每个已实施项补 `验证状态=deferred_to_deepseek`，引用原验收小节和具体新增风险/待测点；集中交接见 `DEEPSEEK_TESTING_HANDOFF.md`。正常小修与自查直接做，避免用记录/验证工程替代功能实现。
6. 原人工确认、本人/门店权限、资金库存事实、默认关闭的功能开关、公司数据隔离及禁止自动上线等规则保持。当前不修改 OS 权限、不启用后台新行为、不调用真实模型；集中测试不等于生产授权。

以下 R3 过程及各项“先测试再进入下一项”文字保留为历史与集中验收合同，执行顺序以本节为准。

**R3 授权优先级**：用户原话“干脆你把这些计划给做完”“按照你的计划，直接进行实施，不再依赖deepseek或者astra low”取代本文及旧交接文件所有要求等待 DeepSeek/用户逐批放行的执行步骤。文中“到点停止/等待审阅/明确放行”在常规源码与隔离验证阶段统一表示：结束本批测试进程→保存证据→Codex 审阅并修复→验收满足后登记 released→继续紧邻批次。它不豁免测试、架构、依赖、真实环境或生产授权。用户另行允许本地调用 DeepSeek；凭据仅用于指定 live gate，不记录密钥，不提前以真实调用替代离线基线。未解决的根本架构冲突、真实环境不可用、员工试用仍如实报告，生产部署不在授权内。

## 使用规则

1. 先读 `AGENTS.md`、当前检查点/交接、`PROJECT_SPEC.md`、`ARCHITECTURE.md`；本文件负责实施次序、精确改动范围及验收。`total_plan.md`保留为用户总计划，本文件细化其内容，未修改总计划原文。
2. 唯一正式计划名为小写 `implementation_plan.md`；直接实施入口为 `CODEX_EXECUTION_PROMPT.md`。旧 DeepSeek/Astra 实施文件仅保留历史；`DEEPSEEK_TESTING_HANDOFF.md` 用于后续集中测试，均不另维护状态。不得建立大小写不同的重复文件。
3. 共 **108个可执行milestone**。M7.1等是分组，不是任务；M7.1.1等才可领取。严格按下方索引数字顺序，每次一个。显式列出的专用依赖和全局前一项均须完成。
4. 每项记录区是唯一实施状态源，保留各轮历史证据。状态为 `todo / in_progress / implemented / done / blocked`；测试结果另记 passed/failed/skipped/error，未验证另记 deferred_to_deepseek。下方检查点表是唯一门禁状态源，交接文档不另维护当前实施状态。
5. 流程为todo→in_progress→done；外部条件/根本冲突→blocked，条件解决且重新核对后回in_progress。M0.2原范围冲突在R2版已限定解除；R2.1仅按审阅补丁修A阶段问题，不重新从M0.1建环境。原有缺陷、过时测试、执行器错误必须按M0.2分别处置，不可互相豁免。
6. 每项先读代码→按允许范围实现→跑定向和受影响原回归→修复→逐条验收→更新记录。到检查点完成本批审阅后继续，不跳过未满足的条件。前项被破坏时，先把当前项改为blocked并写归属原因，再单独重开前项修复；涉及越过已审查范围的修复先按补丁流程裁定，任何时候最多一项in_progress。
7. 每项列出的“允许修改/写入边界”及按用户2026-09-28持续授权登记的必要补丁共同限定生产改动范围，未列出的默认只读。跨文件接线先记录精确范围再实施审阅，不重复申请授权；不得默默扩大架构或原业务规则。当前项记录可维护，外部测试、manifest和验证runner修改后移。
8. 测试日志、缓存、截图、恢复测试、合成数据、付费报告都在仓库外。代码里不存在的模块/路由/runner是本计划要求创建的内容，不能假设已经实现。
9. 多个实施者也必须共用此顺序与状态，不能同时修改不同里程碑。无需每项重复全文；后续只读取当前项、共同规则、对应架构小节和相关代码。
10. 原状态机保持原样。本文所列Plan/Step/Run转换是助手状态；销售/维修/采购等以原API实际 `flow_version`、权限和领域事实为准。不得照用户举例新建另一套订单状态。
11. 没有外部条件时可如实交付已完成源码，但目标不能冒称完全验收。真实模型live gate、独立PostgreSQL/Linux、员工试用分别是M8的外部条件；不得用合成provider、开发者自评或历史结果顶替。

## 强制检查点与放行规则（优先于各项的“进入下一项”）

这里的CP是**实施审阅检查点**，不是运行时Run/工具恢复检查点，也不修改产品中的业务权限。108个milestone编号与顺序保持不变；M0.2.A/B只是同一个milestone的两个阶段。

### R3 连续实施范围与检查点动作

- 本次接手从 **M0.2.A** 继续，先核对 M0.1 记录及执行器差异，不重建环境或跳到 Runtime。
- 到 CP-00A 保存代码、外部测试和证据，追加 v3 报告，保留 v1/v2；A 条件和审阅满足后登记 released，进入 B。M0.2 此时仍为 in_progress，只有 B 满足完整基线合同后才能完成。
- 所有检查点先收尾本批进程、记录实际句柄、保存报告并审阅；问题在当前范围内修复并复验。审阅通过后按用户 R3 连续实施授权进入下一批，不再请求 DeepSeek 交接或逐批确认。
- 自动续轮与剩余预算不代替任何验收。恢复时查本表及记录，继续真实未完成项，不重做已成立的检查，也不继承过期指纹结果。

### 状态、补丁和放行

门禁状态为 `not_ready / awaiting_review / changes_requested / implementation_released / released`。`implementation_released` 按 R4 只允许后续编码，完整验收仍待集中测试。`not_ready`表示本批尚未形成审阅报告；提前停下时报告必须写明未通过项，不能宣称到达验收条件。

1. Codex 更新进度、报告路径，not_ready→awaiting_review；审阅有缺口则 changes_requested，修复并复验后重新审阅。
2. 有必要时将精确补丁保存为 `docs/implementation-patches/PATCH-<CP>-<序号>.md`；不得靠新增补丁降低标准、扩张业务规则或跳过依赖。
3. 只修改当前项及补丁列出的文件，提交同一 CP 的递增报告版本，不覆盖历史失败，不自行改变架构或验收阈值。
4. released 必须具备全部验收、实际审阅结论、报告和指纹，引用用户 R3 连续实施授权。可用同一 milestone 内的独立子代理审阅提高质量，不能把分工变成同时实施后项。
5. 每次仅在本检查点满足后进入紧邻批次。真实条件不足时记录缺项，不能以合成测试替代真实模型、独立环境、员工验收；真实模型已获本地 DeepSeek 调用授权，其他条件按实际具备程度执行。
6. 放行绑定审阅报告版本、受检生产源码/测试/执行器/依赖指纹和计划版本。相关代码变动或补丁扩大范围须更新报告重审；仅回填状态/报告路径不要求自引用哈希。原始run全树指纹照旧保留，不能改历史记录。
7. 当前项出现真实外部阻塞/根本冲突时保留blocked，提交本批提前停止报告。不得用released让未完成依赖自动done。新增基线缺陷的延期只可按M0.2.B的明确补丁规则处理。

必要的小型审阅报告可保存在仓库的`docs/implementation-checkpoints/`；测试、日志、截图、完整diff证据和合成数据仍在V。报告字段、补丁模板和用户转交方式见`DEEPSEEK_HANDOFF.md`。除本项执行记录与当前CP行外，实施者不得擅改本计划正文；正式计划修订由用户审阅指令指定。

### 检查点登记表（门禁唯一状态源）

表中“范围”包含首尾可执行项，按总索引顺序执行；报告默认 `—` 表示尚未生成，放行记录 `—` 表示尚未满足放行验收。每个范围末尾必须审阅。M0.1 已完成，不重建环境；执行器修改后的复验属于 M0.2.A。

| CP | 本批范围 / 必停位置 | 审阅重点 | gate_state | 报告版本/路径 | 放行依据及下一CP |
|---|---|---|---|---|---|
| CP-00A | M0.2.A；完整基线之前 | 隔离语义、测试合同、BASE-001最小修复 | released | docs/implementation-checkpoints/CP-00A-v3.md；v1/v2 及审阅保留 | 用户 R3 直接实施授权；18/43/39/120 实测通过，独立审阅通过，五类指纹见 v3；进入 M0.2.B 至 CP-00B |
| CP-00B | M0.2.B；M0.2结束 | 全部适用基线、失败分类、延期归属 | implementation_released | docs/implementation-checkpoints/CP-00B-v6.md；v1—v5保留 | 用户 R4 明确将测试后移，允许继续 M0.3—M1.1 编码；原基线仍3336/0/1、退出1，符号链接验证移交 DeepSeek，未宣称验收通过 |
| CP-01 | M0.3—M1.1 | 原需求映射、类型与错误合同 | implementation_released | docs/implementation-checkpoints/CP-01-v1.md | 用户R4先实现后测试；映射与纯schema代码审阅完成，AST可解析；原验收后移，继续M1.2—M1.4至CP-02 |
| CP-02 | M1.2—M1.4 | ORM/约束/追加迁移及旧数据兼容 | implementation_released | docs/implementation-checkpoints/CP-02-v1.md | 用户R4编码授权；ORM/迁移静态对照与审查完成，数据库执行验收待DeepSeek；继续M1.5—M1.6至CP-03 |
| CP-03 | M1.5—M1.6 | 备份完整性、四个默认关闭开关 | implementation_released | docs/implementation-checkpoints/CP-03-v1.md | 用户R4编码授权；只读检查、legacy/v2分派与默认关闭配置已审阅，AST可解析；恢复/配置验收待DeepSeek，继续M2.1—M2.3至CP-04 |
| CP-04 | M2.1—M2.3 | 请求号、真实拒绝、无内部commit准备 | implementation_released | docs/implementation-checkpoints/CP-04-v1.md | 用户R4编码授权；纯校验、真实refusal及三条准备路径已源码审阅，AST正常；原故障/幂等/兼容验证待DeepSeek，继续M2.4—M2.6至CP-05 |
| CP-05 | M2.4—M2.6 | 确认快照、幂等、原事实回执 | implementation_released | docs/implementation-checkpoints/CP-05-v1.md | 用户R4编码授权；冻结三段事务、稳定完整行、显式重准备及只读Flow回执已审阅，AST正常；并发/故障/权限/原接口验证待DeepSeek，继续M3.1—M3.3至CP-06 |
| CP-06 | M3.1—M3.3 | 工具对象、持久计划、旧协议兼容 | implementation_released | docs/implementation-checkpoints/CP-06-v1.md | 用户R4连续编码授权；原工具兼容、注册对象与持久DAG及完整行投影已源码审阅，AST正常；运行验收后移，继续M3.4—M3.6至CP-07 |
| CP-07 | M3.4—M3.6 | 原权限、逐事授权、等待条件 | implementation_released | docs/implementation-checkpoints/CP-07-v1.md | 用户R4连续编码授权；真实身份、本人授权生命周期、有限条件与新鲜完成证明已源码审阅，AST正常；测试后移，继续M4.1—M4.3至CP-08 |
| CP-08 | M4.1—M4.3 | 租约与取消、事件、上下文 | implementation_released | docs/implementation-checkpoints/CP-08-v1.md | 用户R4连续编码授权；租约/fence、同事务事件、有来源上下文已源码审阅及静态核对，测试后移，继续M4.4—M4.6至CP-09 |
| CP-09 | M4.4—M4.6 | provider、完整工具意图、模型循环 | implementation_released | docs/implementation-checkpoints/CP-09-v1.md | 用户R4及持续范围授权；provider逐次外发复验、完整检查点恢复、耐久预算/心跳/逐工具让出与同事务唯一回复已源码审阅，静态核对完成；原验收待集中测试，进入M4.7—M4.9至CP-10 |
| CP-10 | M4.7—M4.9 | outbox、无变化零调用、未知结果 | implementation_released | docs/implementation-checkpoints/CP-10-v1.md | 用户R4及持续范围授权；真实源outbox、完整事实核查与去重、未知确认结果协调已源码审阅，AST/UTF-8核对完成；原运行验收待DeepSeek，继续M5.1—M5.3至CP-11 |
| CP-11 | M5.1—M5.3 | REST/SSE兼容、授权事项投影 | implementation_released | docs/implementation-checkpoints/CP-11-v1.md | 用户R4及持续范围授权；真实REST/SSE、旧聊天兼容、授权工作台与本人跟进控制已源码审阅，AST/UTF-8核对完成；原运行验收待DeepSeek，继续M5.4—M5.6至CP-12 |
| CP-12 | M5.4—M5.6 | 通知隐私、MCP互斥、worker退出 | implementation_released | docs/implementation-checkpoints/M5-5-review-v1.md；M5-6-review-v1.md；M5-4-review-v1.md | 集中测试阶段实测：M5.5（7+20）与 M5.6（13+40）在指纹 `fce97834…` 上 passed；M1.4 ORM/迁移一致性 6 项 passed；修复 5 处 MCP 缺陷与 worker 双启动。M5.4 仅源码审阅、进程级/真实环境项未覆盖，故不记 released；继续 M5.7—M5.8 至 CP-13 |
| CP-13 | M5.7—M5.8 | Windows/Linux启动定义与回退 | implementation_released | docs/implementation-checkpoints/M5-7-review-v1.md；M5-8-review-v1.md | 集中测试阶段实测：M5.7（7+16）与 M5.8（7+17）在新指纹上 passed；嵌入顺序、显式 profile、同库同镜像校验、无密钥样例均实测；真实 Windows 预览实例与真实 Linux 部署仍属 M8.7/M8.8，故不记 released；继续 M6.1—M6.8（CP-14—CP-16） |
| CP-14 | M6.1—M6.4 | 客户端归并、恢复、事项工作台、默认入口 | implementation_released | docs/implementation-checkpoints/M6-1-review-v1.md；M6-2-review-v1.md；M6-3-review-v1.md；M6-4-review-v1.md | 集中测试阶段实测：M6.1（15+7）、M6.2（9+7）、M6.3（10+6）、M6.4（6+6）在同一批指纹上 passed；每次前端改动后同指纹回归（workboard/r3/ux/workspaces/oneclick）diagnostic_passed；M6.1 的取消/清理边界随 M6.2 接线同步移动并复跑。仅放行后续编码，不表示测试全部通过或功能启用；继续 M6.5—M6.8（CP-15） |
| CP-15 | M6.4—M6.6 | 默认入口、未发草稿、显式持续跟进 | implementation_released | docs/implementation-checkpoints/M6-4-review-v1.md；M6-5-review-v1.md；M6-6-review-v1.md | M6.4（6+6）、M6.5（13+8）、M6.6（12+7）均已 implemented 并实测通过，退出后 worker 继续与真实浏览器反馈留待 M8.1/M8.4；仅放行后续编码，继续 M6.7—M6.8（CP-16） |
| CP-16 | M6.7—M6.8 | 提醒/核对、窄屏、关闭功能回退 | implementation_released | docs/implementation-checkpoints/M6-7-review-v1.md；M6-8-review-v1.md | M6.7（11+9）与 M6.8（21 条命令全通过：M6.1—M6.8 Node 82 项 + 旧回归 67 项 + Python 61 项 + 语法/生成物检查）均已 implemented 并实测；真实浏览器、真实模型、PostgreSQL、员工试用仍属 M8.x，故不记 released；M6 章节收口，继续 M7.1.1（CP-17） |
| CP-17 | M7.1.1—M7.1.3 | 售前、交车、退订退车 | implementation_released | docs/implementation-checkpoints/M7-1-1-review-v1.md；M7-1-2-review-v1.md；M7-1-3-review-v1.md | M7.1.1（lead 10 项）、M7.1.2（sales_order 9 项）、M7.1.3（aftercare 9 项）均已 implemented 并实测通过，同指纹回归通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.2.1（CP-18） |
| CP-18 | M7.2.1—M7.2.3 | 逐VIN采购、出退库、批量行 | implementation_released | docs/implementation-checkpoints/M7-2-1-review-v1.md；M7-2-2-review-v1.md；M7-2-3-review-v2.md | M7.2.1（9 项）、M7.2.2（9 项）、M7.2.3（9 项）均已 implemented 并实测通过，同指纹回归通过；M7.2.3 先前错报的能力缺口已撤回（JSON 目录不是读取白名单，GET 由活跃路由发现并受原过滤与调用时授权）；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.3.1（CP-19） |
| CP-19 | M7.3.1—M7.3.3 | 接待维修、领退料、返修 | implementation_released | docs/implementation-checkpoints/M7-3-1-review-v1.md；M7-3-2-review-v1.md；M7-3-3-review-v1.md | M7.3.1（9 项）、M7.3.2（9 项）、M7.3.3（10 项）均已 implemented 并实测通过，同指纹回归通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.3.4（CP-20） |
| CP-20 | M7.3.4—M7.3.5 | 理赔核赔、真实进出厂 | implementation_released | docs/implementation-checkpoints/M7-3-4-review-v1.md；M7-3-5-review-v1.md | M7.3.4（claim_order，8 项）与 M7.3.5（gate_visit，8 项）均已 implemented 并实测通过，同指纹回归通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.4.1（CP-21） |
| CP-21 | M7.4.1—M7.4.3 | 精品销售、套餐核销、零售集团 | implementation_released | docs/implementation-checkpoints/M7-4-1-review-v1.md；M7-4-2-review-v1.md；M7-4-3-review-v1.md | M7.4.1（9 项）、M7.4.2（9 项）、M7.4.3（7 项）均已 implemented 并实测通过，同指纹回归通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.5.1（CP-22） |
| CP-22 | M7.5.1—M7.5.3 | 物资采购、预付、仓储 | implementation_released | docs/implementation-checkpoints/M7-5-1-review-v1.md；M7-5-2-review-v1.md；M7-5-3-review-v1.md | M7.5.1（8 项）、M7.5.2（8 项）、M7.5.3（7 项）均已 implemented 并实测通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.6.1（CP-23） |
| CP-23 | M7.6.1—M7.6.3 | 客户档案、服务单、提醒来源 | implementation_released | docs/implementation-checkpoints/M7-6-1-review-v1.md；M7-6-2-review-v1.md；M7-6-3-review-v1.md | M7.6.1（9 项）、M7.6.2（9 项）、M7.6.3（7 项）均已 implemented 并实测通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.7.1（CP-24） |
| CP-24 | M7.6.4—M7.6.5 | 问卷与真实里程日期 | **计划内部不一致（待业主确认）** | — | 本表引用的 M7.6.4/M7.6.5 在计划正文中**没有对应条目**（正文 M7.6 组只有 M7.6.1—M7.6.3，其后直接为 M7.7.1）；按正文编号顺序继续实施 M7.7.1，不自行虚构缺失条目；此不一致由实施者如实登记，不擅自改动业主计划的分组意图 |
| CP-25 | M7.7.1—M7.7.3 | 会员、集团本金、权益 | implementation_released | docs/implementation-checkpoints/M7-7-1-review-v1.md；M7-7-2-review-v1.md；M7-7-3-review-v1.md | M7.7.1（8 项）、M7.7.2（9 项）、M7.7.3（6 项）均已落盘并实测通过；**M7.7.3 权益快照/事实因 member↔customer 维度不匹配待评审补齐**（已如实登记，未伪造）；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.7.4（CP-26） |
| CP-26 | M7.7.4—M7.7.6 | 组合退回、履约、价格候选 | implementation_released | docs/implementation-checkpoints/M7-7-4-review-v1.md；M7-7-5-review-v1.md；M7-7-6-review-v1.md | M7.7.4（8 项）、M7.7.5（6 项）、M7.7.6（9 项）均已落盘并实测通过；**M7.7.5 套餐事实因 purchase↔member 维度不匹配待评审补齐**（已如实登记）；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.8.1（CP-27） |
| CP-27 | M7.8.1—M7.8.3 | 预收、发票、月结冻结 | implementation_released | docs/implementation-checkpoints/M7-8-1-review-v1.md；M7-8-2-review-v1.md；M7-8-3-review-v1.md | M7.8.1（7 项）、M7.8.2（7 项）、M7.8.3（7 项）均已 implemented 并实测通过；真实原库/真实模型/浏览器/员工试用仍属 M8.x，故不记 released；继续 M7.9.1（CP-28） |
| CP-28 | M7.8.4—M7.8.5 | 店间清算、其他收入 | not_ready | — | — |
| CP-29 | M7.9.1—M7.9.3 | 库存仓储、期间入出存、维修领料 | not_ready | — | — |
| CP-30 | M7.9.4—M7.9.6 | 收入成本、活动、汇总统计 | not_ready | — | — |
| CP-31 | M7.10.1—M7.10.3 | 物资整车调拨、运输差异 | not_ready | — | — |
| CP-32 | M7.10.4—M7.10.6 | 原损失找回、跨店原单授权 | not_ready | — | — |
| CP-33 | M7.11.1—M7.11.4 | 基础资料、系统管理、评审边界 | not_ready | — | — |
| CP-34 | M7.12.1—M7.12.3 | 保险、加装、代办 | not_ready | — | — |
| CP-35 | M8.1—M8.2 | 综合恢复、全量不退化 | not_ready | — | — |
| CP-36 | M8.3—M8.4 | 独立PG升级/恢复、真实HTTP浏览器 | not_ready | — | — |
| CP-37 | M8.5—M8.6 | 经live gate授权的真实模型和保留集 | not_ready | — | — |
| CP-38 | M8.7—M8.8 | 隔离Windows/Linux恢复演练 | not_ready | — | — |
| CP-39 | M8.9—M8.10 | 员工试用、发布候选；此后无自动部署 | not_ready | — | — |

CP-39完成后也先提交候选审阅，不能因源码包生成而宣称上线。上述门禁放行不代替真实模型、独立环境、员工数据或生产部署的另外授权条件。

## 总计划与本计划对应

| total_plan工作包 | 具体实施范围 |
|---|---|
| P0 基线与映射 | M0.1—M0.3 |
| P2 数据模型（先于P1持久化） | M1.1—M1.6 |
| P1 确认与拒绝、准备事务 | M2.1—M2.6 |
| P3工具对象、P4身份、P6计划条件 | M3.1—M3.6 |
| P5执行、P6上下文、P7持续跟进 | M4.1—M4.9 |
| 接口、P9通知后端、兼容 | M5.1—M5.5 |
| P11 worker及启动实现 | M5.6—M5.8 |
| P8工作台、P9协作界面 | M6.1—M6.8 |
| P10逐业务适配 | M7的52个最小项 |
| P12及P11实环境验证 | M8.1—M8.10 |

两个必要的顺序调整已在架构中固定：先有表/迁移再冻结提交；先有真实workspace/通知接口再接UI。其余是细分任务，不改变总计划的业务范围。

## 验证命令与记录

在开始每次实施时设置（路径变更只按实际工作树替换RepoRoot，不能误绑其他仓库）：

```powershell
$RepoRoot = (Resolve-Path '.').Path
$V = 'C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'
$VPython = "$V/.venv/Scripts/python.exe"
$ValidationRoot = $V
$ValidationPython = $VPython
```

M0.1创建runner和venv。之后每项只有一个外部统一入口：

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone Mx.y
```

runner已在外部V创建，但M0.2阶段判定和隔离适配仍需按本版修正；不能把M0.1历史自检通过当成当前执行器已经正确。M0.2新增且仅在本项使用`--phase A`或`--phase B`，详细合同见本项；其他milestone继续用上述入口。各项登记准确suite及前置条件，先镜像当前安全源码并设置隔离环境，才能导入app和运行pytest/Node/浏览器。当前仓库没有package.json，不使用npm build。普通定向验证禁止模型联网；真实模型测试明确live gate后才能调用。

记录至少包含：完成日期、修改文件、当前源码指纹、执行命令、退出码、外部报告路径、仍未验证事项。不能只填“通过”。源码指纹必须涵盖未提交改动；仅同一HEAD不证明测试的是同一代码。后续无关文件变化不要求重跑全部旧测试，但最终M8必须对最终候选做完整所需验收。

## 全部里程碑索引

| 序号 | Milestone | 目标 |
|---|---|---|
| 1 | [M0.1](#m0-1) | 建立外部隔离执行器和源码指纹 |
| 2 | [M0.2](#m0-2) | 恢复完整测试依赖并建立当前基线 |
| 3 | [M0.3](#m0-3) | 冻结193项需求、111条工作流及实际操作映射 |
| 4 | [M1.1](#m1-1) | 冻结 Runtime 数据类型与错误合同 |
| 5 | [M1.2](#m1-2) | 规范化计划、步骤与稳定工作项 ORM |
| 6 | [M1.3](#m1-3) | 运行、授权、事件和通知 ORM |
| 7 | [M1.4](#m1-4) | 追加 h53k 迁移并验证旧数据升级 |
| 8 | [M1.5](#m1-5) | 扩展 Runtime 备份完整性校验 |
| 9 | [M1.6](#m1-6) | 四个功能开关与安全默认值 |
| 10 | [M2.1](#m2-1) | 请求号只生成一次，校验函数保持纯净 |
| 11 | [M2.2](#m2-2) | 403 只使用真实拒绝记录提供评审提示 |
| 12 | [M2.3](#m2-3) | 拆出无内部 commit 的卡片构造 |
| 13 | [M2.4](#m2-4) | 冻结人工确认的最终提交与三阶段结果 |
| 14 | [M2.5](#m2-5) | 跨 Run 的准备幂等及完整批量行 |
| 15 | [M2.6](#m2-6) | 只读回执解析框架与通用 Flow 回执 |
| 16 | [M3.1](#m3-1) | 统一工具注册与读、准备、计划分层 |
| 17 | [M3.2](#m3-2) | 对象引用分派及通用 Case 快照 |
| 18 | [M3.3](#m3-3) | 持久 DAG、旧计划兼容与结构版本 |
| 19 | [M3.4](#m3-4) | 可信内部身份与原授权 GET transport |
| 20 | [M3.5](#m3-5) | 逐事授权、暂停恢复与结束 |
| 21 | [M3.6](#m3-6) | 有限等待条件与真实完成判断 |
| 22 | [M4.1](#m4-1) | Run 入队、CAS领取、租约与取消 |
| 23 | [M4.2](#m4-2) | 持久事件序号、展示快照与补读 |
| 24 | [M4.3](#m4-3) | 有来源上下文快照与预算 |
| 25 | [M4.4](#m4-4) | 抽取既有 provider 与资源统计 |
| 26 | [M4.5](#m4-5) | 完整工具意图、逐项检查点及恢复 |
| 27 | [M4.6](#m4-6) | 单次 Run 模型循环与用户输入优先 |
| 28 | [M4.7](#m4-7) | 事务发件箱及确定来源信号 |
| 29 | [M4.8](#m4-8) | 持续跟进轮询与无变化零调用 |
| 30 | [M4.9](#m4-9) | 未知确认结果协调与依赖解锁 |
| 31 | [M5.1](#m5-1) | Run、Plan及原卡回执 HTTP 接口 |
| 32 | [M5.2](#m5-2) | SSE 事件订阅及旧消息接口兼容 |
| 33 | [M5.3](#m5-3) | 授权事项投影与跟进控制 API |
| 34 | [M5.4](#m5-4) | 站内提醒去重和协作隐私 |
| 35 | [M5.5](#m5-5) | MCP 草稿工具兼容及共享互斥 |
| 36 | [M5.6](#m5-6) | worker CLI、关闭和安全健康信息 |
| 37 | [M5.7](#m5-7) | Windows 预览嵌入同实例 worker |
| 38 | [M5.8](#m5-8) | Linux worker 部署定义和开关回退 |
| 39 | [M6.1](#m6-1) | 只增加 Run REST/SSE 客户端和纯状态归并 |
| 40 | [M6.2](#m6-2) | 将发送、恢复和显式停止接入持久 Run |
| 41 | [M6.3](#m6-3) | 实现真实事项侧栏与两列工作台 |
| 42 | [M6.4](#m6-4) | 默认进入助手，同时保持原人工导航与深链接 |
| 43 | [M6.5](#m6-5) | 统一交接守卫与原单/任务/流程“交给助手”入口 |
| 44 | [M6.6](#m6-6) | 每件事的持续跟进与生命周期控制 |
| 45 | [M6.7](#m6-7) | 站内通知、原任务协作和未知结果核对 |
| 46 | [M6.8](#m6-8) | 兼容回归、窄屏与关闭新功能的收口 |
| 47 | [M7.1.1](#m7-1-1) | 售前接待与意向跟进 |
| 48 | [M7.1.2](#m7-1-2) | 版本报价与车辆交付 |
| 49 | [M7.1.3](#m7-1-3) | 退订退车及维修退款纠正 |
| 50 | [M7.2.1](#m7-2-1) | 整车采购逐 VIN 进度 |
| 51 | [M7.2.2](#m7-2-2) | 整车库位及出退库作业 |
| 52 | [M7.2.3](#m7-2-3) | 整车批量导入后的审阅与逐行恢复 |
| 53 | [M7.3.1](#m7-3-1) | 维修预约与实际到店接待 |
| 54 | [M7.3.2](#m7-3-2) | 明细维修、领退料与结算 |
| 55 | [M7.3.3](#m7-3-3) | 原责任返修授权与新增自费 |
| 56 | [M7.3.4](#m7-3-4) | 理赔索赔与实际核赔 |
| 57 | [M7.3.5](#m7-3-5) | 车辆实际进出厂事实 |
| 58 | [M7.4.1](#m7-4-1) | 精品销售及原行退回 |
| 59 | [M7.4.2](#m7-4-2) | 精品套餐规则与套餐销售引用 |
| 60 | [M7.4.3](#m7-4-3) | 精品集团混合支付 |
| 61 | [M7.5.1](#m7-5-1) | 物资采购、实收退货与结算 |
| 62 | [M7.5.2](#m7-5-2) | 采购预付款申请与付款条件 |
| 63 | [M7.5.3](#m7-5-3) | 物资库位收发、移库与盘点 |
| 64 | [M7.6.1](#m7-6-1) | 客户车辆主档与受权历史 |
| 65 | [M7.6.2](#m7-6-2) | 咨询投诉救援与回访单 |
| 66 | [M7.6.3](#m7-6-3) | 客户提醒规则与到期来源 |
| 67 | [M7.6.4](#m7-6-4) | 客户问卷版本与真实答卷 |
| 68 | [M7.6.5](#m7-6-5) | 车辆日期里程观察纠正 |
| 69 | [M7.7.1](#m7-7-1) | 会员卡、续会与积分办理 |
| 70 | [M7.7.2](#m7-7-2) | 集团会员本金与原款退回 |
| 71 | [M7.7.3](#m7-7-3) | 集团权益固定单位 |
| 72 | [M7.7.4](#m7-7-4) | 充值组合购买与整份退款 |
| 73 | [M7.7.5](#m7-7-5) | 混合作业配件套餐履约与退回 |
| 74 | [M7.7.6](#m7-7-6) | 会员价格规则与候选应用 |
| 75 | [M7.8.1](#m7-8-1) | 客户预收抵用、结算及原款更正 |
| 76 | [M7.8.2](#m7-8-2) | 发票申请、外部办理与结果复核 |
| 77 | [M7.8.3](#m7-8-3) | 期间对账与月结冻结 |
| 78 | [M7.8.4](#m7-8-4) | 店间内部清算 |
| 79 | [M7.8.5](#m7-8-5) | 厂家供应商整车其他收入 |
| 80 | [M7.9.1](#m7-9-1) | 整车库存与仓储统计查询 |
| 81 | [M7.9.2](#m7-9-2) | 物资期间入出存查询 |
| 82 | [M7.9.3](#m7-9-3) | 实际维修领退料分析 |
| 83 | [M7.9.4](#m7-9-4) | 物资收入成本对照 |
| 84 | [M7.9.5](#m7-9-5) | 售前活动及维修进出厂统计 |
| 85 | [M7.9.6](#m7-9-6) | 原经营汇总与日报查询 |
| 86 | [M7.10.1](#m7-10-1) | 跨店物资调拨 |
| 87 | [M7.10.2](#m7-10-2) | 跨店整车调拨 |
| 88 | [M7.10.3](#m7-10-3) | 物资运输差异及损失处置 |
| 89 | [M7.10.4](#m7-10-4) | 原损失物资查找与找回 |
| 90 | [M7.10.5](#m7-10-5) | 整车运输异常与原车找回 |
| 91 | [M7.10.6](#m7-10-6) | 跨店原单档案授权 |
| 92 | [M7.11.1](#m7-11-1) | 类型化基础资料 |
| 93 | [M7.11.2](#m7-11-2) | 业务分类字典 |
| 94 | [M7.11.3](#m7-11-3) | 系统管理的原授权查询与人工入口 |
| 95 | [M7.11.4](#m7-11-4) | 真实拒绝记录与评审申请跟踪 |
| 96 | [M7.12.1](#m7-12-1) | 保险报价、外部承保与原款退回 |
| 97 | [M7.12.2](#m7-12-2) | 销售明细加装与原物资退回 |
| 98 | [M7.12.3](#m7-12-3) | 代办及其他客户服务 |
| 99 | [M8.1](#m8-1) | 综合故障与恢复验收 |
| 100 | [M8.2](#m8-2) | 原业务、助手和前端不退化验收 |
| 101 | [M8.3](#m8-3) | SQLite与真实PostgreSQL升级、并发和备份恢复 |
| 102 | [M8.4](#m8-4) | 真实HTTP浏览器、安全会话与界面验收 |
| 103 | [M8.5](#m8-5) | 原101/283真实模型回归 |
| 104 | [M8.6](#m8-6) | 多轮闭环与未调参保留集验收 |
| 105 | [M8.7](#m8-7) | Windows隔离预览启动、关闭和恢复 |
| 106 | [M8.8](#m8-8) | Linux独立worker部署与恢复演练 |
| 107 | [M8.9](#m8-9) | 员工试用与效率验收 |
| 108 | [M8.10](#m8-10) | 发布门槛、交付包与回退清单 |

## M0：外部验证与可信基线



## 统一外部验证合同

- 用户批准后续固定验证根为 NTFS 上的 `V=C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`；原 E: 根保留历史证据，按 PATCH-CP-00B-03 迁移，不复用旧文件系统的验证结论。manifest 绑定当前仓库绝对路径；每次执行记录 HEAD、工作树变化、所有源文件 SHA-256、测试来源/指纹、运行时版本。不能用相同 HEAD 代替工作树指纹，也不把 HEAD 放进命令路径使后续命令失效。
- 统一命令变量：`$RepoRoot='C:/Users/tiefu/.codex/worktrees/edb5/HuaKangOS'`、`$V='C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'`、`$VPython="$V/.venv/Scripts/python.exe"`。换工作树时由执行者设置真实路径并重新绑定 manifest，不自动接管另一个仓库的验证目录。
- M0.1 创建外部 `run_validation.py`；此后唯一测试入口为 `& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone Mx.y`。runner 在任何 app 导入或测试收集前建立隔离环境。各里程碑的命令、用例、前置条件写入外部 `validation-manifest.json`，不能把未知 milestone 当空测试成功。
- 目录：`harness/` 保存隔离执行器；`archive/` 保存恢复的测试源及来源清单；`tests/` 保存新测试；`tests/runtime_domains/` 保存业务适配测试；`tests/frontend/`、`browser/` 保存界面测试；`runs/<run_id>/source/` 保存本次当前源码镜像；`runs/<run_id>/fixtures/`、`tmp/`、`logs/`、`reports/` 保存本次合成数据与证据。每次创建新的 run 目录，禁止覆盖历史报告或复用过期镜像。
- 源码镜像按明确白名单复制当前工作树实际文件，包括未提交修改和本轮新增源码，尊重删除；拒绝符号链接/目录联接越界。排除 `.git`、`.env`（仅允许 `.env.example`）、私有配置、数据库、附件对象目录、备份、日志、缓存和已有虚拟环境。不能复制原预览目录或整份历史验证目录。
- 从归档恢复的只能是测试、测试辅助源、合成夹具定义和冻结评测定义，不得用归档 `app/`、`web/`、`migrations/` 覆盖本次源镜像。需要相对路径的旧脚本，可按原相对位置放入外部 source 镜像并单独标记为测试覆盖层。
- 每个子进程先设置 `APP_ENV=test`、明确绝对合成 `DATABASE_URL`、`SCHEDULER_ENABLED=false`、`SCHEDULER_MODE=off`、`ALLOW_AI_EXTERNAL=false`、空日报 API key、外部合成助手配置、隔离 TEMP/TMP 和附件路径。新测试默认 `LEGACY_BUSINESS_WRITE=false`；原历史兼容用例确需 `true` 时独立进程执行并在报告标记，不能泄漏到 runtime/生产配置验证。
- 主DATABASE_URL必须指向该run的fixtures内、带合成标记的明确SQLite文件；文件连接的相对路径/URI/符号链接/目录联接仍严格校验。测试辅助连接允许真正的匿名`:memory:`，不映射为磁盘文件，不将其用作主DATABASE_URL；不因此放行任意`file:` URI或共享外部库。PostgreSQL必须是显式提供的独立测试实例/专用新库，校验数据库名、服务端标识、合成标记与授权用途。验证器绝不读取仓库`.env`或探测公司/预览库。
- pytest 只能由 runner 在隔离设置后启动；禁止在源码根裸跑 `pytest`。旧 conftest 会建表/删表，必须先核验实际 URL 与合成标记。记录 `app.__file__`、`web/`、迁移路径均来自本次 source 镜像，拒绝从历史快照或真实项目数据路径导入。
- 里程碑状态统一为`todo / in_progress / done / blocked`；测试运行结果另记，不与门禁状态混用。当前实现错误在范围内修复；外部条件或未决架构阻断时blocked。不能删除断言凑通过；经本项明确授权且有当前合同证据的旧测试迁移，必须保留原件、diff及等强度行为核验。依赖blocked的任务不能执行，历史数字不计本轮成绩。前置项done且必需验证满足后，还须检查CP放行；M0.2缺陷延期只按本项严格规则处理。
- 普通测试默认禁止外网。真实模型阶段仅在显式 live gate 下开放已配置官方 provider 地址；密钥由外部安全配置/交互输入取得，不放命令行、日志、manifest 或源码镜像。没有 live gate 的演练必须证明生成调用数为 0。

<a id="m0-1"></a>

## M0.1 建立外部隔离执行器和源码指纹

**状态**：done

**全局顺序前置**：无；先核对本轮阅读清单。

**执行记录**：完成日期=2026-09-27；修改文件=外部V/run_validation.py、harness/{isolation,runtime_guard,sitecustomize,selftest}.py、harness/README.md、validation-manifest.json、binding.json、dependencies.in.txt、dependencies.lock.txt与独立.venv；源码指纹=e1b742356697bd2164a2a6fa70deaf66d5524644f88cebe16258bec914ed5771（本次状态回填前的实际验证快照）；测试结果=13/13通过，0失败、0错误、0跳过，源码与镜像未变化，依赖锁与项目要求匹配，pip check通过、43包锁定；命令/退出码=E:/HuaKangOS-agent-validation/runtime-v1/.venv/Scripts/python.exe -B E:/HuaKangOS-agent-validation/runtime-v1/run_validation.py --repo C:/Users/tiefu/.codex/worktrees/edb5/HuaKangOS --milestone M0.1 / 0；证据路径=E:/HuaKangOS-agent-validation/runtime-v1/runs/20260927T052052Z-89be66088d/run.json及reports/selftest.json、logs/00.log；遗留/阻塞=无。本项仅验证外部执行器，未运行业务回归、真实模型或生产验收；模型调用0次，未改业务源码。下一项M0.2。


**目标**：让后续实现者只能针对当前源码、安全合成数据运行测试，并能追溯每次结果。

**依赖**：读取当前 AGENTS、检查点、R4交接和本轮三份项目文档；只需要源码及 Python 3.11–3.13，不依赖业务改动。

**读取边界**：当前 `requirements.txt`、`requirements-postgres.txt`、`app/config.py`、`scripts/package_source.py`、`alembic.ini`、启动配置及 Git文件清单；归档目录仅枚举测试文件。不得打开或复制真实 `.env`、公司数据库、客户附件或私有助手配置。

**写入边界**：仅 V 下 `.venv/`、`run_validation.py`、`harness/`、`validation-manifest.json`、`runs/` 及锁定的验证依赖清单。仓库只允许更新实施记录；不写测试、日志、数据库或业务源码。

**允许/禁止**：允许安装当前源码要求的依赖及已锁定 pytest/浏览器测试依赖到外部环境；禁止复用项目 `.venv` 或历史 `E:/HuaKangOS/.venv`。不启动业务服务器，不调用模型。

**步骤**：
1. 确认固定 V 尚未绑定其他仓库；记录仓库路径、HEAD、工作树和Python版本。
2. 创建外部 venv、依赖锁定清单与runner；将源码复制、环境设置、路径守卫、日志脱敏、超时清理写为独立harness函数。
3. runner每次生成新run目录及源码清单，设置隔离环境后才能启动测试；测试子进程退出后记录退出码和指纹一致性。
4. 实现 `--milestone M0.1` 自检：尝试缺失URL、repo内DB、外部symlink、继承真实环境变量、旧镜像导入、未知milestone、错误repo绑定，均必须在app导入前拒绝。

**状态转移与异常路径**：不支持的Python、依赖下载失败或目录绑定冲突时里程碑blocked；隔离守卫不拒绝危险路径时测试failed、里程碑保持in_progress修复，禁止后续测试。不得为了跑起来读取预览配置。

**验证命令**（先由本项创建文件，再运行）：
```powershell
py -3.13 -m venv "$V/.venv"
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.1
```
若本机只有3.11/3.12，使用该受支持版本并记录；不能自动安装无关全局运行时。

**完成检查**：
- [x] manifest能区分相同HEAD下的不同未提交源码。
- [x] 未导入app就拒绝非合成库、越界镜像和未知测试项。
- [x] 子进程真实导入路径、环境及依赖版本可核对，无密钥值输出。
- [x] 模型调用0次，仓库无新增测试/缓存/数据，记录M0.1实际结果。

<a id="m0-2"></a>

## M0.2 恢复完整测试依赖并建立当前基线

**状态**：implemented

**验证状态**：deferred_to_deepseek。R4 用户将测试阶段后移；实现与修补已完成，原完整 B 仍为 3336 passed / 0 failed / 1 skipped、退出 1。原符号链接安全断言移交集中测试，CP-00B-v6 仅放行后续编码。以下 v5 阻塞记录保留为授权变更前历史，不再是当前编码门禁。

**全局顺序前置**：M0.1 done。

**PATCH-05 完整复验记录（最新，2026-09-28）**：strict `20260927T163115Z-f97fd5d948` 18/18；第三诊断 `20260927T163202Z-1d7da6404c` 60/60、退出 0。随后新完整 B `20260927T163618Z-574f417642` 全部 41 命令实际执行，2781 pytest＝原 2124＋新增 657，实际 2780 passed / 0 failed / 1 skipped；其它 556 passed，合计 **3336 passed / 0 failed / 1 skipped**。原 36 失败节点本轮 setup/call/teardown 全部 passed；无 missing/extra/duplicate/not_run/非终态/超时。原 session 63205 自然退出 1、验证进程 0；40 命令 complete，唯一未通过组是含符号链接 skip 的第十一业务组。strict 五指纹与全部输入/依赖检查一致，独立核对 2915 文件哈希无差异。完整报告及哈希见 CP-00B-v5，旧失败、原件与历次诊断保留。

**集中测试首轮完整 B（2026-09-28，合并 origin/main 后）**：run `20260928T064850Z-ed840e406e`，41 条命令全部实际执行，**2741 passed / 39 failed / 1 skipped**，7 条命令不完整（其中 1 条为符号链接 skip）。逐条归因后 38 项为过时测试合同/测试替身、2 项为产品缺陷：
- 产品修复：`registry_for_config` 缺配置时回退旧目录（M3.1 记录）；`resolve_preparation` 不再照抄模型自带的 request_id（M2.1 记录）。
- 测试合同对齐：`PATCH-CP-00B-08`（假网关 body_schema/refusal_metadata/permission_hint/规范操作号、信封 request_id、M2.2 真实拒绝提示、`last_request.run_id`、403 归类、R3 脚本化工具调用补 `type=function`、月结定义 21→现行 22、行指纹按原列集合比较）。
- 复验（同指纹 `46c3960e85c2e98fc41cdb9c0366341c5b60987cb10d1f88cbc0d6589bea4ff6`）：`b05-business-02` 161/0（`20260928T090316Z-f2eeac2f7b`）、`b05-business-03` 114/0（`20260928T083034Z-2b3ba7a4bc`）、`b04-check_assistant_r3` 与 `b05-business-09/10/13` 诊断全通过（`20260928T090849Z-7ca79b4be4`）。
- 唯一未通过组仍为含符号链接 skip 的 `b05-business-11`；该断言需真实可创建符号链接的环境，属既有环境缺口，不改为通过。整轮复跑与最终登记见后续 CP-00B 记录。

**集中测试基线复跑（2026-09-28，最终）**：run `20260928T092636Z-3bff5089f3`，源码指纹 `3b3e4ba71ecbf684f3107cfb756faba0a065942c955fa95331558efcae3565f3`。41 条命令全部实际执行：
- `baseline_pytest` 22 条：**2780 passed / 0 failed / 1 skipped**（含 M0.2 自带的 657 项合同套件与 21 组业务回归）。
- `python_script` 18 条（含 5 项 Node 前端检查、目录/工作流/清单/迁移等脚本）：全部 successful。
- `baseline_collect` 1 条：完整清单通过。
- 唯一 `complete=false` 的是 `b05-business-11`（104 passed / 0 failed / 1 skipped），skip 仍是当前环境无法创建文件符号链接的既有缺口，未改为通过。
与 2026-09-27 基线（3336 passed / 0 failed / 1 skipped）相比：同一批命令口径下失败清零，新增 M1.4/M5.5—M5.8 等外部套件；M6.1/M6.2 另按各自 milestone 单独留证。

**当前阻塞与恢复**：原 `tests/test_private_files.py::test_symlink_file_and_root_rejected` 因创建链接进入 OSError/skip 分支，文件读取和目录根拒绝断言未执行。本轮没有具体 Windows 错误码，不把此前探测 WinError 1314 写成本轮观测。须具备真实文件及目录符号链接创建条件后由统一 runner 复验；不能以硬链接/目录联接、删除断言、跳过或延期产品缺陷替代。之前关于系统条件的用户选择仍待答复，未改系统设置。CP-00B 不放行，M0.3/Runtime 未开始，真实模型调用 0。BASE-001 按已 released 的 CP-00A-v3 和本轮原节点通过回填 resolved，保留外部 before/history，不改旧 run 哈希。状态/报告回填在审计之后，不宣称回填后的整树字节仍等于冻结快照。

**以下为历史时点记录**：其中“最新/当前/下一步”等原文只表示当时状态，以以上最新完整复验与阻塞记录为准。

**R3 C: 完整基线记录（最新）**：strict `20260927T140154Z-bbad0660d9` 18/18；完整 B `20260927T140257Z-053b24940f` 已自然退出 1、进程收尾。41 命令完整登记和执行，34 通过/7 失败；原 2124＋新增 399＝2523 pytest 节点，2486 passed / 36 failed / 1 skipped；其它 556 检查通过，合计 3042 passed / 36 failed / 1 skipped。无 missing/extra/duplicate/not_run，全部前后输入和依赖一致，strict 五指纹匹配。独立终态审阅通过可归属性检查，不代表 CP 放行。PATCH-04 的 27 目标正式通过、missing_report 关闭；8 旧合同＋28 执行适配问题按 PATCH-05 修补，符号链接原节点仍实际跳过。见 CP-00B-v3；M0.2 未 done，后项未开始，真实模型调用 0。

**PATCH-05 当前实施记录**：18 个限定外部文件已合并、独立审阅并按指纹应用。合并审阅发现并修正了新 URI 纯测试缺 reporter 身份的夹具冲突，安全守卫和原断言保留。新增五模块实际只收集到 244 节点（46/41/124/9/24），未执行测试、导入产品或访问数据库/网络；登记后 b01 为 643 节点，预计完整 pytest 2767 节点，须由正式 runner 再收集确认。319 原件不变，原 41 命令的范围、顺序、超时不变；新 strict、正式诊断和完整 B 尚未通过。合并 manifest SHA `abe78c0ac0ee18ab5916dc3cd1201b96ca34f7d3e99db2ee747ba998685e4e2f`；实际应用/登记证据在 `V/review/CP-00B-05/`。不新增生产差异，不将登记或诊断写成完整验收。

**PATCH-05 第一轮正式复验**：strict `20260927T155446Z-0be208b45d` 已实际 18/18、退出 0。诊断 `20260927T155523Z-0df4da21e5` 已结束、退出 1，全部输入前后一致；完整 collect 2767，原 2124 精确保留。b01 为 374 完整 passed、1 teardown 错误及 268 setup 级联错误：根因为诊断运行把两份完整清单放进约 161 KB 的环境变量，Windows 无法恢复该值。原 7 组业务定向均未执行，不能写成已复验。正在按 PATCH-05 附记缩减环境传递内容，完整列表仍冻结于诊断选择/command，权限交集和完整性标准不变。新指纹下需再次 strict、正式诊断与完整 B；CP-00B 未放行。

**当前修补状态**：上述环境长度修复的两文件候选已独立审阅并应用，新增 5 回归实际收集完成：诊断模块 129，五个新模块共 249。只更新 b01 minimum 为 648 和现有 addition 指纹/历史；全量预计 2772，仍须正式 runner 确认。证据为 `V/review/CP-00B-05/contract-size-independent-review.json`、`contract-size-application.json`、`contract-size-registration-verification.json`；旧失败与原 319 文件均保留。接下来按当前冻结输入重新 strict→相同诊断→完整 B，未将 collection 写成通过。

**第二轮终态与最新修补**：诊断 `20260927T161041Z-076dad3ad0` 已真实退出 1：2772 完整 collect、648 合同全部通过、全诊断 778/5/1；原 31/36 失败关闭，运输 109/109，PATCH-04 的 27 目标均通过。五个剩余失败同属 Windows venv orig_argv 身份误拒。仅外部 fixture_profiles 及其纯测试的两文件修补已独立审阅并应用，开发实收 profile 55（旧 46＋新增 9），五模块合计 258；b01 minimum 已登记为 657、完整预期 2781。证据和输入哈希见 CP-00B-v4。下一步新 strict→55＋5 局部诊断→41 命令完整 B；不复用旧诊断代替完整验收，符号链接缺项保留，后续里程碑未启动。

**R3 C: 首轮基线记录（历史）**：strict `20260927T131721Z-08d5e63d84` 18/18；B `20260927T131802Z-08e49c6b4c` 收集 2504 唯一节点，原 2124 保留。21 命令完整、1089 passed；第二组 161 节点中 118 incomplete，另 43 加后续 1810 共 1853 not_run；七个实际失败事件另保留。原文件解析安全用例的 open monkeypatch 拦住执行器证据写入，造成 missing_report，统一入口退出 1、进程已结束；全部前后输入/依赖检查通过。分类、处置与限定修改见 CP-00B-v2 / PATCH-CP-00B-04；不把局部结果计为完整通过。

**PATCH-04 实施登记（历史时点，现已由本轮 27 目标正式关闭）**：执行器和两份外部测试的限定修改已独立审阅；19 项 reporter 纯合同通过。保留全部 319 原件、原 2124 节点范围与 41 个 B 命令；新增后预期 2523 pytest 节点、399 合同节点。317 份本次未改 overlay 与上一轮 C: 三类冻结证据一致，来源和原件未覆盖。原解析器安全节点和七个旧失败节点须在新的完整 B 实际通过，不以开发检查或前轮片段代替。

**R3 B 早期修补实施记录（历史）**：PATCH-CP-00B-01 的 P1/P2/P3 已实施并独立审阅；PATCH-CP-00B-02 已补齐 9 个精确原件，原件总数 319。新增 Python→Node 守卫纯合同 54/54、Node 嵌套进程纯合同 43/43 通过，原断言保留；开发检查均不代替正式验收。完整 pytest 预期 2504（原 2124 + 新 380），仍为 41 个命令，顶层 Node 仍为原 76 节点。唯一新增生产差异仍是便携手册 6 处已审文案。用户批准后续验证根迁至 C: NTFS，PATCH-CP-00B-03 仅复制输入、修正外部辅助程序的运行根并重新登记；旧 E: 的 run 和归档不动。迁移后须重新 strict+B，不能复用旧卷或两轮中止的局部成绩。符号链接权限未满足时不能宣称完整基线通过。下面 A/首轮记录为历史时点事实。

**R3 A 完成记录（历史时点）**：A 已完成，M0.2 继续 in_progress，现进入 B 登记与完整基线。strict run `20260927T113830Z-d5de052b37` 18/18；A run `20260927T113902Z-7cf01ce103` 43/43、39/39、120/120 全部通过，0 failed/error/skipped/xfail/xpass/timeout。报告身份和逐节点完整，五类输入与 strict 相等，运行前后无漂移，依赖双检通过；A phase_complete=true、milestone_complete=false。生产仍仅改 claimed_actions 纯文本 helper，BASE-001 有限合同关闭；配置 loader 未改。正式报告及独立审阅结论见 `docs/implementation-checkpoints/CP-00A-v3.md`；用户 R3 授权下 CP-00A released。v2 缺口及历史见 review-v2。B 尚未执行，M0.3 及后项未开始，真实模型调用 0；当前不得把 M0.2 标 done。

**R3 B 首轮记录**：新 strict `20260927T121534Z-9465484290` 18/18；B `20260927T121610Z-e5de8ccf21` collect=2440（2124 原 + 316 新），41 命令登记、20 命令完成，866 passed / 5 failed / 1 error。确认两个 CMD 测试依赖遗漏后中止本批，首业务组部分事件与后续未执行项均不计通过；统一入口退出 1，进程已收尾。原报告保留，实际中止见 run 内 `reports/operator-interruption.json`；审阅见 CP-00B-v1，补丁 PATCH-CP-00B-01 尚待独立审阅和复验。M0.2 仍 in_progress，CP-00B changes_requested，无后项开始、无真实模型调用。

**R2.1审阅裁定**：下方v1执行记录及17/21/39/12通过数作为历史证据保留，不等于CP-00A通过。审阅发现R1验证判定、R2精确配置例外、R3文案回归、R4输入完整性/报告问题，执行范围与追加验收以`docs/implementation-patches/PATCH-CP-00A-01.md`为本项补充合同。用户授权修补后执行；不改M0.2状态为done，不开始B。修补后的实际记录追加于此，不覆盖v1或原run。

**执行记录**：完成日期=未完成（A阶段到CP-00A停止；PATCH-CP-00A-01已执行并复测）。历史状态原因=BASE-001未获准修改而停止，R2/R2.1计划已把限定修复归属M0.2.A。A阶段第一批（v1，run `20260927T093923Z-27f36d7a68`/`20260927T093938Z-cdcb3f18da`，21+39+12项）被审阅判为不通过：新增文案回归2处、判定8处误判、配置例外过宽、绑定口径不可成立；详见`docs/implementation-checkpoints/CP-00A-review-v1.md`与`docs/implementation-patches/PATCH-CP-00A-01.md`。本批按补丁P1—P4重做并复测：M0.1严格自检run `20260927T105258Z-ed40d78a79` 18/18通过（原17项+按命令与节点授予配置合同1项）；M0.2 `--phase A` run `20260927T105903Z-a72790c990` 三项命令全部complete且`phase_complete=true`、`milestone_complete=false`、`incomplete_reasons=[]`、`strict_reference.fingerprints_matched=true`——a1（两处迁移合同+配置节点+27条句式表全量回归）collected 36/terminal 36/passed 36、a2 R3T3离线39项、a3（匿名内存迁移+两处gift迁移+runner判定/配置合同）collected 17/terminal 17/passed 17，全部0 failed/0 skipped/0 error。判定改为collect与execute分开、逐nodeid生命周期与身份核对、超时/跳过/重复/额外节点/缺终态一律拒绝；配置例外改为manifest按command_id与精确nodeid登记并将合同冻结进run（`command-context/`），删除全局`HUAKANGOS_FAKE_CONFIG`名单；`phase_complete`现同时要求输入未变与依赖双检，`milestone_complete`恒false。生产改动仍仅`app/business_assistant_service.py`的`CLAIM_*`常量、`unquoted`、`clause_is_affirmative`、`claimed_actions`。本批源码指纹`ae0fb2f474cea48d1875c788b313a89f044e46f8f0a4c8e2ce302438e3b61502`、可绑定harness指纹`dedab6c59460115df037fe578254067f495b5c6bbc3dd7d582971f62a17f6718`（两次run一致）、依赖锁sha256`3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930`。完整基线/B阶段未运行，M0.3未开始，真实模型/PG/浏览器/员工试用均未执行；SSE瞬时展示边界、配置测试三态语义与句式覆盖边界列为待审阅（见CP-00A-v2第6节）。


**目标**：证明现有原业务、助手及前端回归确实测试当前工作树，固定本轮比较基线。

**依赖**：M0.1 done。

**读取边界**：`E:/HuaKangOS-cleanup-20260927-082922/removed/scripts/`、对应归档 docs/冻结场景；可选完整原回归来自 `E:/HuaKangOS-ui-validation-20260927/source/tests/`，仅取测试与其实际依赖，并记录来源。该目录存在旧app/data，不得复制。若依赖不完整，按交接从原Git历史1f884fb取得测试源；不存在该历史则blocked，不能声称当前ZIP含历史。

**涉及文件及允许修改**：

| 位置 | 唯一允许职责 |
|---|---|
| `app/business_assistant_service.py` | 只修改`claimed_actions`及其必要的同文件私有纯文本判断helper，修BASE-001；不改其他服务函数 |
| `V/run_validation.py::main` | M0.2阶段选择、有限命令分派、证据完整性和结果判定；保持其他milestone合同 |
| `V/harness/isolation.py::{db_path,validate_environment}`、`runtime_guard.py::install` | 主库守卫不变；辅助匿名内存连接例外、限定离线配置测试环境 |
| `V/harness/selftest.py` | 补充隔离/判定回归，不删除原安全检查 |
| `V/harness/baseline.py`、`baseline_results.py` | 定向/完整suite选择、逐节点结果与独立分组证据；不替换当前业务源码 |
| `V/tests/baseline/overlay/tests/conftest.py`、`overlay/scripts/assistant_eval_support.py::configure_isolation` | 撤销内存连接落盘替换，保留安全标记；按明确fake配置运行原离线测试 |
| `V/tests/baseline/overlay/tests/test_business_assistant.py` | 仅下文两个旧文案测试的当前合同迁移；原业务行为断言保留 |
| `V/tests/baseline/test_m02_claim_contract.py`、`test_m02_harness_contract.py`（新增） | BASE-001边界及执行器合同测试；通过runner导入当前镜像 |
| `V/validation-manifest.json`、`V/tests/baseline/{applicability,baseline_defects}.json` | 精确注册、分类、来源及缺陷归属，保存版本差异 |
| V内恢复清单、测试适配diff、本次run报告、`m02-progress.json` | 保留旧证据，追加当前进度/指纹和本版裁定；不得改写旧run结果 |
| 本文件当前项/CP行、`docs/implementation-checkpoints/CP-00A-vN.md`和`CP-00B-vN.md` | 真实状态与审阅摘要；完整日志仍留V |

**禁止修改**：原业务API/schema/RBAC/门店/财务/库存/迁移，`business_assistant_prompt.py`、`_conversation`纠正提示和轮数、`business_assistant_stream.py`、前端SSE处理、模型provider业务配置逻辑。禁止为了旧测试恢复“逼模型新增卡”的提示；禁止`已.*生成`等宽泛匹配、完整NLP重构、自动业务提交、取消隔离/外网守卫、从归档拷业务代码。BASE-001之外的生产修复必须先交审阅补丁，不归到M4.6偷偷扩范围。

### M0.2.A：先纠偏和定向复验，到CP-00A停止

按A1至A6顺序执行；它们是本项内部步骤，不创建多个in_progress。

**A1. 冻结输入与恢复入口**

1. 查实际进程与绑定，确认没有本V的活动测试；不复用旧session id。保留现有环境、依赖锁和已恢复308文件，按清单核对缺失，不从头安装/恢复整套。读取M0.1历史报告并记录此后harness变化。
2. 留存当前源码、overlay、harness、manifest、依赖锁的独立指纹和完整文件清单。诊断历史照存，不把171通过数混进新计数。
3. 冻结每个run输入：测试期间不能编辑该run镜像或所加载的harness/overlay。需要修改时先停完该run，再生成新run；新旧报告不能拼接冒充一次运行。

**A2. 修复runner阶段与判定**

1. 在现有parser增加仅用于M0.2的`--phase A|B`；M0.2缺phase或其他milestone携带phase，给明确非零参数错误，不默认启动B。manifest分别登记A的必需命令和B的完整清单；本轮不能执行B。
2. 每条命令需保存kind、准确argv、selection/节点清单、开始结束、exit、非空结果与完整性。命令成功、阶段通过、milestone完成分开记录。A定向全过可exit 0并写`phase_complete=true,milestone_complete=false`；不能据exit 0把M0.2写done。
3. 删除“任何milestone都必须selftest>=13”的全局判定方式，改为按注册suite检查各自必需证据；不得直接删自检要求。完整注册为false、空选择、未识别kind、缺报告、collect失败、超时均不能判为完整基线通过。诊断的maxfail退出不计完整运行。
4. 重新运行M0.1严格模式自检，独立run、`legacy_compatibility=false`；保留原13项并追加新项。不要把它塞进legacy=true的M0.2子环境，也不删除“未注册legacy=true应拒绝”检查。
5. 当前runner只有selftest/collect/pytest分派。允许增加**有限的离线Python检查脚本、Node --test、workflow --check**分派，只接受manifest审过的当前镜像内固定相对路径和参数数组，拒绝任意shell命令/越界路径。A仅运行已登记的定向Python脚本；B的Node/workflow完整套件待放行后运行。不得假设runner已经支持。
6. 同run多条pytest不得覆盖`pytest-results.json`或混淆events。选择给每条命令独立`command_id`结果目录，或每组独立run；记录采用的方案，完整聚合按B3处理。继续保留逐节点JSONL和阶段耗时，失败即能读取明确错误，不等整批超时才见日志。

**A3. 恢复测试原语义并保持隔离**

1. 主DATABASE_URL仍是run/fixtures内带标记的明确文件。仅在SQLite辅助连接审计入口允许字面值`:memory:`直接连接内存；其余全部走原文件守卫。拒绝未审URI、共享缓存、越界和无标记文件；不允许主库为内存。
2. 撤销conftest中把`:memory:`变匿名磁盘文件的两个入口替换；允许保留对本run中新合成文件的限定标记。证明两个内存连接互不共享、关闭后内容不保留、没有新增anonymous磁盘库。迁移辅助测试仍在合成环境运行。
3. 离线助手脚本会使用`enabled=true`和固定假key，产品配置测试还会临时设置ALLOW_AI_EXTERNAL并测试synthetic=false/true。为**精确登记的离线脚本/配置测试节点**建立fake配置例外，保留原断言意图；只接受run内合成配置与已知假key，不读取真实配置，默认网络出口始终阻断。不得将所有测试改enabled=false或把普通运行的禁联网条件整体放开。
4. 普通测试模型调用仍为0；fake provider调用次数另列。测试真实配置拒绝的节点不等于live授权。增加负例，证明未注册节点、任意key/URL不能获得例外，实际外连不能发生。A不修改产品配置加载代码。

**A4. 当前合同迁移与BASE-001最小修复**

先读`docs/R3T3-真实报告审阅与修复.md`第21—29行附近、当前service的`claimed_actions`/`_conversation`及外部`check_assistant_r3t3.py`。行号仅定位，实际符号为准。

- 保留archive原件。将`test_a_claim_without_a_tool_call_is_sent_back_once`的“逼模型真的准备”旧说明改为“纠正无工具/无卡事实”；将旧提示语`没有生成任何待确认卡`的逐字断言迁移为核验当前系统消息中的**实际卡数量为0、不能为圆话新增业务、仍服从员工原请求**。保留纠正只一次、最终补信息回复和数据库proposals为空的行为断言。
- `test_the_card_count_told_to_the_model_comes_from_the_database`把旧`实际生成 2 张待确认卡`迁移为当前`实际准备或复用 2 张待确认卡`语义，仍从真实数据库核对2张而非mock工具宣称数。仅这两处已获准迁移；保存原文、diff、对应合同和新断言说明到V/tests/baseline，其他语义冲突先报告。
- 修`claimed_actions`漏掉明确陈述`第 7 批 4 张待确认卡已真实生成，请逐张核对后点击确认。`。目标仍是阻止没有实际卡的已完成宣称；现有R3T3否定/将来/条件/分句规则要保留。必要helper保持纯函数，不访问DB/网络。
- 不只机械增加`(?:真实)?`。新回归至少覆盖下表；按当前支持的窄句式处理，不追求识别所有自然语言。未匹配文本绝不能作为业务完成证据。

| 输入/场景 | 必需结果 |
|---|---|
| 上述明确已真实生成、实际0卡 | 触发一次纠正；fake provider先返回错误宣称，再返回如实说明；最后仍0卡 |
| `确认卡已生成`等现有明确陈述 | 保持已有真阳性行为 |
| `尚未生成确认卡`、`会准备确认卡`、`如果确认卡已生成，请核对` | 不当成已完成陈述 |
| `“确认卡已真实生成”是一个错误说法`、`请解释“确认卡已真实生成”这句话` | 引用说明不误触发 |
| `确认卡已真实生成吗？`、`未证实确认卡已真实生成` | 疑问/未证实不误触发 |
| 只查询的正常回复，无准备请求 | 不要求新增卡，不产生业务写入 |
| 实际有本轮有效卡的正常回复 | 数量以数据库为准，不额外纠正或准备 |
| 纠正轮中合法的原请求准备 | 保持原工具及权限语义；本修复不把纠正轮全局变只读，不放开自动确认 |

每个场景保存预期及结果。至少一项针对原漏报的回归须在本轮改动前镜像失败、改后镜像通过；原件/改后都留证据，不在运行中回写镜像。拒绝业务写入的保证由原确认边界验证，不能仅凭文本断言。

**A5. 定向验证和已知范围**

1. manifest A只登记：独立严格隔离自检证据、两个迁移测试、BASE-001及上表回归、一组匿名内存迁移辅助检查、`check_assistant_r3t3.py`离线回归、runner非空/失败/超时/注册完整性判定。每项有当前结果；缺任一不能写phase_complete。
2. 现有SSE可能先展示模型文字，再在完整回复阶段纠正。BASE-001修复**不保证前端瞬时绝不显示错误宣称**，在CP报告列为独立待审阅边界，不改stream/frontend、不宣称已闭环。由审阅补丁决定是否调整后续M4/M5范围。
3. 已知全量setup成本高（一次局部记录约84%耗在建删表），A不做测试数据库架构优化。先保留语义及增量日志；后续必要优化必须证明隔离、触发器、约束和清理等价，不能仅凭断言AST相同。

**A6. 交付CP-00A**

更新BASE-001为`owner=M0.2.A`并保留旧blocked_unassigned历史、证据及当前修复/复测状态；只在定向证据成立后标该缺陷resolved，不代表M0.2完成。更新外部进度指向本版，不覆盖旧失败报告。生成CP-00A报告，M0.2保留in_progress，门禁awaiting_review，然后停止。

**A阶段命令**（phase参数由A2实现后使用；M0.1独立严格自检）：

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.1
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.2 --phase A
```

**CP-00A验收条件（与整个milestone的完成检查分开）**：

- [x] 新旧严格隔离自检完整；辅助内存连接不落盘，主库/路径/网络/假配置边界仍有效。R2.1：精确command/node配置例外需按补丁复验。（v2：M0.1严格run `20260927T105258Z-ed40d78a79` 18/18；未登记命令/节点、越界配置、外连均拒绝）
- [x] runner能区分定向成功、注册未完成、空集合、失败/超时，必需结果均非空；不会混写分组报告。R2.1：完整节点/终态、collect-only与timeout+exit0判定需修补。（v2：collect与execute分开判定，逐nodeid生命周期与身份核对，reviewer 5个探针全部按预期）
- [x] 两项旧断言有当前合同映射、原件/diff及等强度行为核验，未恢复强制准备卡的旧提示。
- [x] BASE-001修前失败/修后通过及反例通过，数据库卡数/只查不写/原确认边界保持。R2.1：指定句已有证据，但新增误报/漏报必须关闭。（v2：27条登记句式+6个行为场景全部通过，含P3表内16条）
- [x] 当前离线R3T3脚本运行，模型真实调用0；SSE瞬时展示边界如实列出。
- [x] 报告绑定当前源码/测试/harness/依赖指纹，范围核对无越界；**不执行完整基线，M0.2不设done，停CP-00A**。R2.1：补输入漂移/依赖门禁、实际diff及准确v2报告。（v2：`strict_reference`绑定+输入未变+依赖双检参与`phase_complete`；报告见CP-00A-v2）

### M0.2.B：仅在CP-00A明确放行后建立完整基线

**B1. 登记**：核对CP-00A获准报告和补丁，无未完成的必要修补。恢复原助手脚本完整import依赖图、101/283冻结定义及辅助文件；现有308文件按清单核验，不假设文件数就是完整性。登记实际适用原业务pytest、助手Python/Node、workflow --check全部命令；每项有来源/hash/适用理由。5个废止maintenance用例的排除沿用精确文件/hash与AGENTS依据，不扩大排除。

**B2. 运行**：先collect对齐完整inventory，再逐组运行；关闭A的diagnostic_nodeids和maxfail截断作为完整成绩的限制。允许单独诊断失败，但不能把该次结果当整组验收。每组退出/超时后立即保存逐项结果，不能有已知失败仍只有点号的长时间黑箱。完整列表至少包括恢复后的适用业务pytest，`check_ux.py`、`check_workspaces.py`及实际适用`check_assistant_*.py`，四个已恢复Node脚本（check_ux/check_workspaces/check_assistant_r3/check_assistant_workboard），当前源码`build_workflow_guides.py --check`；以恢复清单核对遗漏，不用glob盲跑付费/有副作用脚本。

**B3. 聚合**：每组独立报告，完整baseline.json逐nodeid/场景列passed/failed/error/skipped/not_run和理由，含setup/call/teardown。重跑失败时关联原失败报告，不能删历史。复用已完成组仅在相关生产源码、overlay、harness、依赖锁、运行配置、选择清单指纹全部一致且该组完整时允许；任何变化须重跑受影响组，不能因HEAD一样就拼接。对无法证明无影响的变更重跑相关整组。完整inventory每项须有最终判定；未执行和超时残留不能计完整。

**B4. 按下表处理失败，禁止混为“历史问题”**：

| 类型 | 判据与处理 |
|---|---|
| harness/环境错误 | 路径、内存、配置、依赖、证据判定污染；在本项允许边界内修复并重跑，不能备案为产品缺陷 |
| 已过时测试合同 | 对照当前AGENTS/业务接口/变更文档给出精确冲突，保留原断言；A列的两例可迁移，其他例提交补丁审阅，不能自行放宽 |
| 本项引入回归 | 在本项范围内修复并复测，不能延期为基线缺陷 |
| 原有生产缺陷 | 精确节点、错误、未包含本项生产修复的原安全镜像复现、当前镜像复现、影响、指纹及证据；没有允许文件/函数归属则提前停CP-00B请求补丁 |
| 已废止能力 | 仅明确被AGENTS/用户废止的能力可登记不适用；精确文件/hash/理由，不用目录级忽略或任意xfail |
| 外部条件缺失 | 记录缺失依赖/实际条件为blocked/not_run，不计通过，不伪造真实模型/浏览器/PG结果 |

**B5. 有限延期与结束**：默认完整适用基线通过才完成。若确有不阻断前置能力的原有生产缺陷，可在CP-00B提前报告，M0.2仍未done；由用户批准的补丁写出精确缺陷、已有milestone中的修复文件/函数、关闭测试、受影响依赖及最晚关闭点，且证明按顺序无依赖环。仅填owner名字不构成归属。批准后若全部必需测试都已执行、余下失败仅为这些明确延期项，M0.2可done，但必须保留`baseline_test_result=failed / baseline_disposition=registered_defects`及真实失败数；下一批仍需CP-00B放行。安全/隔离/确认/权限失效、未分类或无法定位缺陷不可延期；M8.2和最终发布不接受未关闭备案。

**状态转移与异常路径**：旧blocked→开始A的in_progress→CP-00A等待审阅（仍in_progress）→明确放行后B→满足完成条件done→CP-00B等待审阅。普通失败在允许范围内修复；越界/合同未决/外部阻塞则blocked并提前出报告，等补丁解决后恢复原阶段，不跳任务。M0.2任一阶段都不改变原业务状态机。

**B阶段命令**（只有CP-00A放行后）：

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.2 --phase B
```

**整个M0.2完成检查**：

- [x] A阶段条件满足，CP-00A有真实审阅/补丁/放行记录，所有必要补丁已复测。
- [x] 恢复来源、依赖、适用清单、适配diff及101/283定义hash可追溯。
- [x] 当前app/web/migrations与受检源码一致，未测归档旧业务代码；分组没有混合来源/配置或覆盖报告。
- [x] 全部适用Python/助手/Node/workflow有逐项结果及完整性检查，未拿历史通过数或collect数当通过数。
- [ ] 真实模型0调用，未访问公司库/原预览库；未分类失败、环境污染、缺失必需套件均已解决。（本轮无模型/业务数据访问，但原符号链接必需安全断言尚未执行，环境条件未解决。）
- [x] 原有缺陷已修复复测，或仅剩用户明确批准的精确延期补丁；BASE-001已关闭，无宽泛豁免。
- [x] CP-00B审阅报告已保存，完成后停止，未自行开始M0.3。（v5 保存本轮阻塞结论，CP 并未放行，M0.2 未 done。）


## 核心实现：M0.3 与 M1—M5

以下均为待实现任务。新增源码只允许每项列出的文件及函数范围；所有其他生产文件默认只读。每项必须同时新增对应外部定向测试、登记runner manifest并更新本计划状态。精确测试文件见每项命令段。

<a id="m0-3"></a>

## M0.3 冻结193项需求、111条工作流及实际操作映射

**状态**：implemented

**验证状态**：deferred_to_deepseek；当前完成可追溯映射产物，集中测试按原验收条件后续执行。

**产物指纹**：`V/capability-matrix.json` SHA256=`13118e04866f02eb82182bac9593291d2e75300dfc7d8c56fef292e76ab7d9dd`；源指纹记录生成时快照，不包含本段后续状态回填。

**全局顺序前置**：M0.2 done。

**执行记录**：实现日期=2026-09-28；产物=`V/capability-matrix.json`，可追溯193需求、111流程、52个M7、207需求关联及70人工入口；源码指纹=产物的source_manifest逐文件SHA256（HEAD f735de2，含当前工作树）；源码静态路由385项，其中按gateway原规则179查询、127准备、79封闭，289 reviewed项均找到真实注册路径。审查修正共享flow路由造成的过宽领域归属，入口/原kind与原API权限分别保留；可证明调用和同域候选不混用。测试=未执行，验证移交DeepSeek；剩余8个M7无独立发布流程但保留观察到的原人工入口，typed-master/flow-master/vehicle-catalog边界及动态schema、原动作可用性均明确未验证。所有条目acceptance=unverified、availability=unknown；不导入app、不访问数据库、不调用模型。本项原测试/manifest登记后移，产物及生成脚本在V/review/M0.3。


**目标**：为每个需求建立源文件、原入口、岗位/门店、已评审操作及M7适配归属，让后续不会漏业务。

**依赖**：M0.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：docs/原始功能需求表.docx；docs/workflow-source/；web/workflow-guides.json；web/moduleworkspaces.js；app/business_assistant_capabilities.json；app/business_assistant_gateway.py；total_plan.md。

**允许修改**：仅外部 $V/capability-matrix.json、$V/tests/baseline/test_capability_matrix.py 和manifest；仓库只更新本项记录。外部测试和本项实施记录为共同允许项。

**禁止修改**：不修改原需求、不为减少缺口删除入口、不把静态可检索当业务已验收、不导入归档旧app。

**实施步骤**：

1. 按原需求名和业主修订列193条，保留别名与原编号；发布目录列111条实际ID。数量若已发生合法变动，报告差异和来源，不强凑数。
2. 在M0.1隔离镜像中扫描实际FastAPI路由与gateway reviewed catalog，按原规则提取operation_id=METHOD + route.path，保留path占位符和参数schema。
3. 建立需求→入口→工作流→read/prepare operation→领域adapter/M7编号→原权限→测试来源映射；封闭管理面记人工入口，不强造模型能力。
4. 每条初始验收状态unverified；已知原缺口/无只读可用性证明单列。更新后续manifest的原回归映射，不重新扩大读写目录。

**状态转移**：此项只建立可追溯清单；unverified不自动变passed，完成静态映射不代表完成193项业务。

**异常路径**：缺原需求源/重复ID/路由与reviewed目录失配须定位；数量变动未经当前依据解释则blocked，不能随意删行。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/baseline/test_capability_matrix.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.3
```

**验收条件**：

- [ ] 193原需求和111发布流程逐条有来源与人工入口，原需求名仍可检索。
- [ ] 全部M7适配有实际operation映射或明确只读/封闭说明，未按猜测生成operation。
- [ ] 记录未支持/未知事实条件及归属；模型调用0、业务写0。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-1"></a>

## M1.1 冻结 Runtime 数据类型与错误合同

**状态**：implemented

**验证状态**：deferred_to_deepseek；本轮实现纯类型模块及静态审查，原完整验收后移。

**全局顺序前置**：M0.3 done。

**执行记录**：实现日期=2026-09-28；修改文件=`app/assistant_runtime_schemas.py`；SHA256=`8c566e7ce88f81b9a05edb2a5c467ec3ae52b30988137884d6283b1ca6c34732`；实现严格DTO/五条件/entry_context/状态/事件最小载荷/冻结快照及canonical SHA256。root及独立审查补齐retail_bundle_sale、请求号一致性、空白输入、UTF8标量检查；只导入stdlib+pydantic，未导入app或建库。AST静态解析退出0，不代表DTO运行通过；测试/模型调用=0；记录=`docs/implementation-checkpoints/CP-01-v1.md`。所有原定向、往返、异常及原回归留DeepSeek执行；无编码阻塞。


**目标**：把本轮接口约定实现为可单独导入的严格类型，后续任务只使用这一份定义。

**依赖**：M0.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_models.py；app/business_assistant_api.py；app/business_assistant_forms.py；ARCHITECTURE B2/C/D/E4/F。

**允许修改**：新增 app/assistant_runtime_schemas.py。外部测试和本项实施记录为共同允许项。

**禁止修改**：不建表、不导入app.main/db、不注册HTTP路由、不改变原API schema。

**实施步骤**：

1. 逐字段实现ObjectRef、EvidenceRef、Snapshot、ReceiptLookup、Plan/Run/WorkspaceView及ARCH中的状态枚举；unknown/null和空列表不可混用。
2. 实现五种条件的判别联合类型；拒绝额外字段、任意表达式、未知类型；钱/量/ID沿原严格校验，不做浮点推断。
3. 定义Run创建/取消、followup启停、entry_context请求类型；请求不得接受actor/store/role覆盖值。
4. 错误输出沿原detail；新错误码只作为附加机器字段，锁定422/404/403/409/503的适用边界。
5. 实现ARCH C3冻结snapshot canonical SHA-256纯函数，完整性检查与确认共用；不改原领域digest。

**状态转移**：本项无业务状态变化；只允许ARCH D1列出的枚举；非法值校验失败422。

**异常路径**：对象ID类型错误、未知条件、不可证明动作available_actions=unknown、回执inaccessible均有独立类型；不能默认为成功。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_1.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.1
```

**验收条件**：

- [ ] 无app导入副作用；全部DTO序列化字段与ARCH一致。
- [ ] 严格入参拒绝额外权限字段、半截工具JSON和不合法枚举。
- [ ] nullable版本、三值事实、request_id以及UTC时间往返不丢信息。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-2"></a>

## M1.2 规范化计划、步骤与稳定工作项 ORM

**状态**：implemented

**验证状态**：deferred_to_deepseek；当前只实现ORM与静态审查，不导入app或创建schema。

**全局顺序前置**：M1.1 done。

**执行记录**：实现日期=2026-09-28；新增PlanStep/WorkItem，扩展WorkPlan默认engine_version=1/goal_version=1/active及检查时间，Proposal仅新增nullable唯一source_work_item_id，models末尾注册。原卡/原JSON历史不补造工作项；当前图由后续v2服务独占。新WorkItem保留StoreScoped且显式store FK无列默认门店，服务仍须传入已授权门店；命名唯一/FK/状态/版本及step需plan约束已写，三表引用环由named use_alter FK及后续分阶段迁移处理。nullable JSON使用none_as_null，区分SQL NULL和空数组。AST静态解析退出0；未导入app/建库/测试，原新库约束、旧导入和唯一性用例移交DeepSeek。文件SHA256：assistant_runtime_models.py=`f64332761ccd38719530abd8e74c157f12f7979689c062d788473c257f762b6b`；business_assistant_models.py=`d3de6ea9a45631b49d85f8a76c0468f1fdffe6f8af56a4a13a58c9641cc88bd8`；models.py=`9b7c08efd36a47b58f6269970e453738b569fa30109fd9e1c020c45e55bbc224`。无编码阻塞，M1.3继续增量扩展。

**集中测试补充（2026-09-28）**：ORM/迁移全链一致性实测（run `20260928T060914Z-5e452d642a` passed）发现 `business_assistant_work_plans.store_id` 在已发布 h52j 上有 `stores` 外键、而 ORM 的 StoreScoped 未声明，属 ORM 与物理库漂移；按"迁移只追加不重写"的要求在 ORM 侧补齐该列声明（`PATCH-M1-2-01`），其余 13 张助手表的列/外键/索引/唯一约束/CHECK 名称两侧一致。business_assistant_models.py 指纹随该修复变化，见 PATCH-M1-2-01。


**目标**：建立计划DAG和跨Run准备幂等的数据库实体，不接入运行行为。

**依赖**：M1.1 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_models.py；app/models.py；app/db.py；migrations/versions/h52j_assistant_work_plans.py；ARCH C。

**允许修改**：新增 app/assistant_runtime_models.py 的PlanStep/WorkItem；修改 app/business_assistant_models.py 中AssistantWorkPlan扩展及AssistantProposal.source_work_item_id；app/models.py仅注册导入。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改原FlowCase/Task/财务表，不新增第二份可写steps，不执行迁移或启动服务器。

**实施步骤**：

1. 保留原字段和旧默认；WorkPlan加engine_version=1、goal_version、status、next_check_at。context_snapshot_id外键留到M1.3与目标表一起定义，避免本项建schema时未解析引用。
2. 实现PlanStep及(plan_id,key)唯一索引，依赖数组存稳定key；WorkItem字段逐项按ARCH C3，包括read/prepare、intent_version、supersedes。PlanStep保留nullable proposal_id以关联真实旧卡，(plan_id,proposal_id)唯一；不为旧卡补造WorkItem。
3. Proposal只有nullable唯一source_work_item_id外键；WorkItem不再建反向proposal外键。
4. ORM注册避免循环导入；本项外部测试只在新合成schema上检查模型定义，不替代M1.4迁移。

**状态转移**：旧计划保持engine_version=1；新类型尚不启用；重复WorkItem意图键或重复卡关联由唯一约束拒绝。

**异常路径**：旧卡source_work_item_id=null可共存；跨owner/store/session引用由后续服务层及完整性检查拒绝，不能以外键存在代替授权。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_2.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.2
```

**验收条件**：

- [ ] 旧助手模型导入兼容，旧记录默认值不产生Run/Grant。
- [ ] 数据库约束拒绝同键WorkItem和一工作项两卡。
- [ ] 不存在循环Proposal/WorkItem外键或原业务表变更。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-3"></a>

## M1.3 运行、授权、事件和通知 ORM

**状态**：implemented

**验证状态**：deferred_to_deepseek；当前只落盘模型与静态审查，不执行schema或迁移验证。

**全局顺序前置**：M1.2 done。

**执行记录**：实现日期=2026-09-28；assistant_runtime_models.py追加Run/RunItem/ContextSnapshot/RunEvent/FollowupGrant/WakeEvent/Notification；WorkPlan增加nullable context_snapshot_id命名use_alter FK。有store列的新表保留StoreScoped并显式store FK，子表通过必需Run/Proposal/Plan归属；login hash引用无FK。两库active Grant/confirmation部分唯一、触发/尝试/事件/通知去重、冻结字段互斥、正版本和计数CHECK、append-only快照/事件ORM保护已实现；root审查补齐plan_id与goal_version同空/同非空，避免NULL绕过版本绑定。没有消息时不创建ContextSnapshot，through_message_id保持原真实消息FK非空。AST静态解析退出0；未导入app、建库、测试或启动worker。全部DDL、唯一性、logout、权限及恢复用例待DeepSeek。SHA256：assistant_runtime_models.py=`f34ba680654a4ebf6623b0138284b0e73eb74fb25219a7cd89f20f5eef0f1509`；business_assistant_models.py=`26613e0ec480b55805590433856bc700428f32419657386037684799a9712028`；models.py注册沿M1.2。无编码阻塞。


**目标**：为队列、恢复、持续跟进和站内提醒建立唯一持久记录。

**依赖**：M1.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：已实现 assistant_runtime_models.py；app/business_assistant_models.py；app/security.py；ARCH C3。

**允许修改**：app/assistant_runtime_models.py 增加Run、RunItem、ContextSnapshot、RunEvent、FollowupGrant、WakeEvent、Notification；必要注册导入；app/business_assistant_models.py增加WorkPlan.context_snapshot_id外键。外部测试和本项实施记录为共同允许项。

**禁止修改**：不写worker/网络调用；不保存Cookie、CSRF、reasoning；不为LoginSession建立阻止logout删除的FK。

**实施步骤**：

1. 按ARCH表逐字段实现，RunItem confirmation允许run_id=null且必须proposal_id，其他kind必须run_id。 同项增加WorkPlan.context_snapshot_id，Run必须包含已验证entry_context。
2. 添加Run触发键、RunItem尝试键、RunEvent序号、WakeEvent signal_key、Notification来源键唯一索引；Grant每plan一个active的SQLite/PostgreSQL部分唯一索引。
3. Run的lease/fence/stop_requested/event_seq、WorkPlan goal_version及Grant绑定保留独立含义。
4. 状态CHECK、非负版本/序号、必要FK与查询索引写明；无需立即接旧service。

**状态转移**：Run初始queued；RunItem pending；WakeEvent pending；Notification unread；Grant只由后续人工启用服务创建。

**异常路径**：两个active Grant竞争、非法confirmation空引用、重复事件序号均失败；不能靠先查后插保证并发唯一。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_3.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.3
```

**验收条件**：

- [ ] ARCH C3所有表字段及索引在合成SQLite可检查。
- [ ] 允许历史人工确认无Run，拒绝其他无Run项。
- [ ] logout删除登录会话不被Runtime FK阻止。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-4"></a>

## M1.4 追加 h53k 迁移并验证旧数据升级

**状态**：implemented

**验证状态**：deferred_to_deepseek；本轮仅追加迁移文件并静态对照ORM，全部升级/恢复执行后移。

**全局顺序前置**：M1.3 done。

**执行记录**：实现日期=2026-09-28；新增`migrations/versions/h53k_assistant_runtime.py`，SHA256=`6a0730c851a7b940199dee121156f606452bf9d36ba325b5698c80f1ebe4bb36`。静态确认原唯一h52j、h53k未占用；追加后源文件唯一head h53k，无重复revision。九新表依赖顺序与153列/42Unique+Check/33索引和最终ORM一致；最后反射batch扩展旧Plan5列、Proposal1列，旧数据不补造Run/Grant/快照，历史迁移/env未改。downgrade默认拒绝，显式布尔合成标记+全非版本表为空才可回退，PG另需RC隔离及锁后二验。AST/源码审阅完成，未导入app、连接数据库、执行迁移或测试；旧数据指纹、FK、SQLite升级及PG验收全部移交DeepSeek。报告CP-02-v1，无编码阻塞。


**目标**：使带旧会话、卡和计划的h52j数据库可无损升级到本轮schema。

**依赖**：M1.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：migrations/env.py；migrations/versions/h52j_assistant_work_plans.py；新ORM；alembic.ini。

**允许修改**：新增 migrations/versions/h53k_assistant_runtime.py；migrations/env.py仅在确需注册新模型时修改。外部测试和本项实施记录为共同允许项。

**禁止修改**：不重写任何历史迁移，不对公司/原预览库upgrade，不用create_all代替迁移。

**实施步骤**：

1. 验证当前唯一head及h53k未占用；发现新head即报告根本冲突。
2. 在单个新revision内按依赖建表、加nullable关联、创建索引；SQLite batch模式遵守现有FK约定。
3. 用合成h52j夹具保存旧业务行/旧助手行指纹，再upgrade并核对所有字段与外键；不为旧卡补造提交快照。
4. 检查ORM与迁移一致；downgrade仅用于一次性空合成库的迁移测试，不作为生产回退方案。

**状态转移**：h52j→h53k；旧engine_version=1、无Grant、无Run；旧业务状态完全保持。

**异常路径**：迁移头冲突/数据约束异常停止；部分失败仅丢弃本次合成库重新验证，不能删除实际数据解锁。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_4.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.4
```

**验收条件**：

- [ ] 当前head升级成功且原业务行指纹相同。
- [ ] 旧会话/卡/计划可读；SQLite foreign_key_check为空。
- [ ] 新建库从头迁移与h52j升级得到相同schema；PostgreSQL实测留待M8.3明确记录。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-5"></a>

## M1.5 扩展 Runtime 备份完整性校验

**状态**：implemented

**验证状态**：deferred_to_deepseek；本轮实现只读检查及接入，不打开任何数据库执行验证。

**全局顺序前置**：M1.4 done。

**执行记录**：实现日期=2026-09-28；新增assistant_runtime_integrity.validate，只读检查九表与旧表扩展的完整标记、会话/员工/门店归属、同计划DAG、WorkItem/卡与替代链、Grant/Run目标绑定、真实消息来源、冻结提交与共用canonical摘要、事件连续序号、通知/唤醒引用。新来源卡已执行但confirmation整行缺失也拒绝；旧无快照卡、退出后的登录引用、合法queued/running/uncertain仍保留。report_query必须引用同范围read/GET工作项；原生业务对象/回执事实仍由原服务判断，不按当前权限变化判历史损坏。旧plan validator先检查Runtime，engine1沿原规则，engine2只使用规范化图；backup原业务规则全部保留，仅合并检查计数。独立代码审查发现的授权目标版本、安全ID、步骤报错定位及整行缺失已修复。三文件AST解析退出0；未导入app、连接数据库或执行测试。源SHA256：assistant_runtime_integrity.py=`14735dfce73cc5f4d5b80e5c0ac67eebfe67e897a85be67d3156c00e17b1556b`；business_assistant_plan_integrity.py=`de99588189d6223ef74cd04c79f1c8e23594466c39e35203a8f604e80bd56e3f`；backup_integrity.py=`5959d8d13621f43e9b03e0db4ff73e7e2dc4b189f6ffc3d6045e7109b05710dc`。原损坏注入、恢复回归、合法中间态全部待DeepSeek；source_refs现仅有限JSON对象数组，后续持久层需遵守实际引用合同，无编码阻塞。


**目标**：让备份恢复能发现Runtime孤儿、跨店关联、DAG损坏及不合法冻结提交。

**依赖**：M1.4 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/backup_integrity.py；app/business_assistant_plan_integrity.py；app/private_file_backup.py；新ORM与h53k迁移。

**允许修改**：新增 app/assistant_runtime_integrity.py；app/backup_integrity.py 接入；原 business_assistant_plan_integrity.py仅legacy/v2分派。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改变备份文件格式、不覆盖旧业务校验、不自动修复/删除异常记录。

**实施步骤**：

1. 沿原validate(connection)风格只读校验新表；缺表按原schema版本识别，不能把损坏h53k当legacy跳过。
2. 检查owner/store/session一致、plan/step依赖无环、WorkItem/Proposal关联、Grant目标版本和active唯一。
3. 核对RunItem confirmation的归属/必需字段/摘要一致性及RunEvent序号唯一；不要把未开始或故障中的合法状态当损坏。 使用M1.1纯摘要函数，不自选算法。
4. 在外部副本逐项注入孤儿/跨店/环/伪冻结摘要，保存每类明确错误。

**状态转移**：合法运行中备份可恢复原状态；异常只报告，不执行状态修复。

**异常路径**：legacy计划无RunItem不报损坏；新confirmation缺最终快照必须拒绝；未完成Run不等于数据库损坏。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_5.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.5
```

**验收条件**：

- [ ] 每种损坏能定位表/记录而不输出私密payload。
- [ ] 原完整性规则仍运行；新规则不会改库。
- [ ] 备份含合法queued/running/uncertain数据可通过结构校验。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m1-6"></a>

## M1.6 四个功能开关与安全默认值

**状态**：implemented

**验证状态**：deferred_to_deepseek；仅配置与features合同接线，不导入Settings或读取真实.env。

**全局顺序前置**：M1.5 done。

**执行记录**：实现日期=2026-09-28；Settings新增assistant_home_enabled/runtime_enabled/followup_enabled/notifications_enabled，沿用原flag严格解析，默认false；followup开启但runtime关闭明确ValueError。RuntimeFeatures同步此一致性约束；.env.example仅添加四个无密钥默认false示例。已审查原生产Host/Cookie/ClamAV、日报与供应商设置未改；原status继续独立提供ready/message，features实际响应和legacy分支将在M5接入，本项无worker启动。Python源AST解析退出0；未导入Settings/读取真实.env或运行测试。SHA256：app/config.py=`1897ef9ef35bfb8f56dc319b8eab79e6fe4a63bbd169aff745322a75946ddfd6`；app/assistant_runtime_schemas.py=`97c8b52e6fe558af7db9493ddf8a7d7a0f4411b060d53d416667af1feb76da70`；.env.example=`e5386bc04722c7a87859c33cd97badd052717c5fd3f67b071d6335b5dee2d087`。四开关组合、非法值、生产配置与无副作用原验收待DeepSeek，无编码阻塞。


**目标**：在业务改动接线前固定关闭和回退行为。

**依赖**：M1.5 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/config.py；.env.example；app/business_assistant_service.py:status；ARCH H。

**允许修改**：app/config.py 新开关解析；.env.example仅无密钥示例；schema features定义必要对齐。外部测试和本项实施记录为共同允许项。

**禁止修改**：不打开默认功能、不改变日报/模型供应商/支付/文件安全配置，不读取真实.env。

**实施步骤**：

1. 增加HOME/RUNTIME/FOLLOWUP/NOTIFICATIONS四开关，全部默认false；followup=true但runtime=false配置报错。
2. 保留原Settings验证；生产HTTPS/Cookie/Host/ClamAV/legacy限制不降级。
3. features只反映服务器实际开关；模型配置是否就绪单独给safe ready/message，不暴露endpoint/key。
4. 关闭runtime要求旧执行器仍可用；实现接口时依本项契约接分支，不现在修改旧conversation。

**状态转移**：默认legacy模式；显式开关启用新能力；关闭不删数据，不撤销已成功原业务。

**异常路径**：非法布尔值及矛盾组合明确失败；模型未配置不影响原人工页面及真实待办。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m1_6.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M1.6
```

**验收条件**：

- [ ] 四开关默认false；互斥组合和生产配置回归通过。
- [ ] 输出没有凭据、内部路径或模型私有配置。
- [ ] 没有导入时启动worker的副作用。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-1"></a>

## M2.1 请求号只生成一次，校验函数保持纯净

**状态**：implemented

**验证状态**：deferred_to_deepseek；仅实现请求号生成与纯校验，不启动测试或导入app。

**全局顺序前置**：M1.6 done。

**执行记录**：实现日期=2026-09-28；gateway.validate_operation删除内部UUID生成，只深拷贝规范化/原schema校验；prepare_proposal仅在原body schema声明request_id且缺key时为body副本生成一次，探测及最终补填重验沿用同值，已有非法/空值不替换，无幂等字段不加号。检索全部三个校验调用点，单张/批量/typed准备均经此入口；forms原保护字段和严格金额数量转换未改。独立审阅发现历史probed卡可能缺号，已在pending复用时明确409要求取消重建，不静默修改旧payload/digest或在确认时补号。AST解析退出0；未导入app或执行测试。SHA256：gateway=`ad6113585321f707851ec98ae20d0185f3f0056c0116bfd12b42befe17f68be8`；service=`5a6ca3e013e5346c97730219d22861699aae6cc4d3af440a0b07de4274b90e77`。多次校验不变、探测值不落库、历史缺号卡、非幂等操作和原严格字段回归均待DeepSeek；原请求号是接口允许的文本键，不擅自收窄为UUID格式。无编码阻塞。

**集中测试补充（2026-09-28）**：完整基线复跑发现"模型自带 request_id 时服务端照抄"与《请求号只生成一次》冲突，并使冻结确认（`SubmissionSnapshot` 要求 body 的 request_id 与冻结值一致）在确认时 409。已改为只按 schema 判定 `generate_request_id`：模型/员工自带值先被零值探测键替换、落库前丢弃，准备落库时由服务端生成唯一提交标识；纯校验层确认时不换键。复验见 PATCH-CP-00B-08 §1-P2 与 run `20260928T090316Z-f2eeac2f7b`（`tests/test_business_assistant.py` 161 项全通过）。


**目标**：消除补填及确认再次校验时重生成原业务request_id的风险。

**依赖**：M1.6 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_gateway.py:validate_operation；app/business_assistant_service.py:prepare_proposal/apply_answers；app/business_assistant_forms.py。

**允许修改**：app/business_assistant_gateway.py 的validate_operation；app/business_assistant_service.py 中准备阶段生成request_id的调用；必要 forms探测调用。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改原业务request_digest算法、原schema必填规则、金额数量解析；不添加通用自动重试。

**实施步骤**：

1. 列出validate_operation所有调用者，先用外部用例固定原读/准备/补填行为。
2. validate_operation仅规范化/校验传入值；缺request_id是否允许由原schema决定，不再内部uuid。
3. 准备阶段仅为原API声明的幂等字段生成一次服务器请求号；临时探测值永不写入原草稿，已有request_id原样保留。
4. 确认补填仍严格解析原生字段；填答案只改允许字段，不能覆盖operation/path/身份/request_id。

**状态转移**：准备→补填→再次校验期间请求号不变；非法答案保持原卡待补，不进executing。

**异常路径**：空/错误UUID、数字边界、中文枚举label误作value、临时探测占位均显式拒绝；不能四舍五入通过。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_1.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.1
```

**验收条件**：

- [ ] 同一张卡多次补填/显示/校验的原request_id一致。
- [ ] 没有业务幂等字段的操作不硬加字段。
- [ ] 钱/量/ID严格边界及旧枚举回归通过。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-2"></a>

## M2.2 403 只使用真实拒绝记录提供评审提示

**状态**：implemented

**验证状态**：deferred_to_deepseek；先实现真实拒绝附加字段及gateway消费，原权限与评审规则保持。

**全局顺序前置**：M2.1 done。

**执行记录**：实现日期=2026-09-28；main.note_refusal从原审计行提取{id,category,can_escalate}，commit成功后返回；排除路由/无记录/失败返回None，http_error保留原detail/status/headers，仅成功记录时附加refusal。gateway只接受真实响应中正整数ID/既有category/严格bool，拒绝正文猜测与伪造结构；authority/amount/rule按元数据分类，缺记录403标refused，不自动声称权限不足。评审提示引用确切记录号并指向原人工页面；catalog subset本地拒绝无审计，不再标为permission。独立审阅确认旧service会将任何403 hint拼为权限文案，因此写操作403/amount暂不设置顶层hint，保留原detail和真实refusal，避免错误标签；M2.4确认重构时按真实category消费。原分类器、队列、自批与权限规则未改。AST解析退出0；未导入app/执行测试。SHA256：app/main.py=`1206fed6b1bbc2d192569a1879e128df9249303e3fef8b9117f213909c36f3ad`；gateway=`e2ee659e029219f7e7b8ef658006010901cfd8265ef3b2f5a836ee8b60d36c82`。真实403/422、规则拒绝、自批、审计失败、畸形refusal及原HTTP兼容验收全部待DeepSeek，无编码阻塞。


**目标**：将权限拒绝与业务规则拒绝分开，只有服务器持久记录的可评审refusal才给评审入口。

**依赖**：M2.1 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/main.py:note_refusal/http_error；app/escalation_service.py；app/business_assistant_gateway.py:permission_hint/invoke。

**允许修改**：app/main.py 的note_refusal返回及异常响应附加字段；app/business_assistant_gateway.py 拒绝分类；必要 app/business_assistant_presentation.py 展示映射。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改原权限、评审人队列、自批规则或403 detail；不凭文案正则猜权限。

**实施步骤**：

1. note_refusal成功提交后返回最小{id,category,can_escalate}；未记录/被排除的路由返回null。
2. HTTP异常保持原detail/status，附加真实refusal；gateway只消费这个字段。
3. 自批、状态不符、金额/规则问题按真实category展示；申请评审仍走原人工入口。
4. 拒绝记录写失败只去掉评审提示，不能把原拒绝变成功或吞掉业务错误。

**状态转移**：业务仍403；可评审记录→可展示入口；记录缺失/不可评审→只展示原拒绝。

**异常路径**：伪造refusal ID、外部工具文本称可审批、不存在收件队列均不创建评审或业务。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_2.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.2
```

**验收条件**：

- [ ] 自批拒绝不显示权限申请；真实可评审拒绝引用可读取原记录。
- [ ] 原HTTP调用方仍能读取原detail。
- [ ] 拒绝审计失败不导致额外业务写或泄密。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-3"></a>

## M2.3 拆出无内部 commit 的卡片构造

**状态**：implemented

**验证状态**：deferred_to_deepseek；本项拆分只读解析和无commit保存，故障注入/回归后移。

**全局顺序前置**：M2.2 done。

**执行记录**：实现日期=2026-09-28；service新增内部ResolvedPreparation/ResolvedBatchPreparation，resolve只查询归属并严格校验，build/flush/persist无commit/HTTP，默认commit_preparation一次保存并对异常rollback。业务表单与case工具完成全部原授权GET/候选/版本/parse_fields后返回内部解析对象；业务展示label/result快照在卡片flush之前加入，同事务保存，移除旧第二次commit。run_tools新增仅Python关键字resolve_only，未加入任何模型schema；直接/业务批量完整保留每行对象或错误，默认逐行保存及原响应保留。校验临时请求号仅在副本，Resolved.body不保留占位，真实UUID在去重后首次build生成；同员工/门店/会话/岗位/access_version保存前重验。read_phase guard拒绝待写变更及当前已flush未commit的卡片事务；独立审阅发现的默认batch在guard前读取问题已修为入口及inspect前检查。原digest/30分钟有效期/问题字段/原确认流程未改；三文件AST解析及直接commit/network调用静态扫描正常，未运行测试或app。SHA256：service=`5e5b6f16f027f64ff66d3bb928141fe880b5ca2d739a7497e424957d7fbd248d`；business_tools=`95b54ed98a5c19b5d989e2ae15eb0e2bca22a7d05dd86446735bcb1782e41e92`；case_tools=`06dfe61cd435a33d450e864d0d9f4dafeeb88994dc8c0ea98594868e7bc0ed57`。三入口故障回滚、并发flush冲突、展示同事务、旧结果形状/批量/字段回归与事务guard均待DeepSeek；具体WorkItem/Step/event原子写入由后续项接线，本项不宣称Runtime已可用。


**目标**：为后续卡片、工作项、步骤、事件同事务提交提供最小可复用原语。

**依赖**：M2.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_service.py:prepare_proposal/prepare_operations/proposal_digest；新WorkItem/Proposal模型；app/business_assistant_business_tools.py:prepare/handle；app/business_assistant_case_tools.py:handle_case_tool；ARCH B3。

**允许修改**：app/business_assistant_service.py 仅拆build/flush helper及原兼容包装；必要 app/business_assistant_forms.py 调用签名；business_assistant_business_tools.py与business_assistant_case_tools.py仅拆只读resolve/无commit persist调用，保留旧默认包装。外部测试和本项实施记录为共同允许项。

**禁止修改**：不整文件重写，不让helper执行原业务API，不改变卡片digest/30分钟有效期/必填问题。

**实施步骤**：

1. 沿ARCH B3提取resolve_preparation，复用原候选/表单/原单版本/严格字段校验，完成全部原授权GET后返回ResolvedPreparation或needs_source；此时无待提交卡。
2. 提取persist_preparation/build_proposal/flush_proposal，只add/flush不commit；展示label/result.business_presentation也同事务，去除Runtime路径高层helper的第二次commit。
3. 旧prepare_proposal/business prepare/case prepare保持默认resolve后commit及原返回；service.run_tools仅增加服务器内部选择新路径的接线，不接受模型指定事务或授权参数。
4. 外部故障用例覆盖business_v1、legacy case及直接prepare三条入口；resolve期间不持卡片事务，persist之后故障使card/关联/展示快照一起回滚。

**状态转移**：构造未提交→flush→调用方commit后prepared；异常rollback后无孤卡。

**异常路径**：flush唯一冲突不能内部commit半成品；兼容包装失败保持原错误语义。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_3.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.3
```

**验收条件**：

- [ ] business_v1、case、直接准备及批量原回归通过，无任何隐藏第二次commit。
- [ ] 新helper无隐藏commit，失败后数据库无残留。
- [ ] UI所需questions/fields/digest未变化。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-4"></a>

## M2.4 冻结人工确认的最终提交与三阶段结果

**状态**：implemented

**验证状态**：deferred_to_deepseek；仅实现冻结与确认事务，真实业务及故障注入后移。

**全局顺序前置**：M2.3 done。

**执行记录**：实现日期=2026-09-28；service确认路径与新增assistant_runtime_receipts冻结helper已落盘。员工归属/digest/期限/答案及原schema校验后，以同一事务冻结最终payload和真实request_id、唯一confirmation与Proposal.executing；首次提交失败不调用原API，实际调用仅用冻结副本且无重试。结果另事务按Proposal/RunItem版本与状态保存；原接口成功但助手保存失败时保留成功观察并向旧UI明确显示需核对，不宣称回滚。helper拒绝同卡不同冻结摘要，不为旧已处理卡补造历史。真实refusal按服务器元数据解释，取消及旧批量继续执行语义保留。两轮独立源码审阅修正了展示窗口遗漏正常结果卡及rollback后异常处理访问过期ORM对象；全部目标卡只从真实授权记录补入。AST解析退出0，无app导入/DB/模型/测试执行。SHA256：service=`6bb88413c3bd35c26ba65d9993dee402b60e8fa24fc6b676d61ba21c6733147d`；receipts=`643214a9ebec1ec8494d6bcf3493fb364cee92924eadcbd864d96bc6b56e1190`。并发双击、冻结失败、业务成功后助手提交失败、超时/崩溃、补填逐字段一致、旧批量及UI原回归全部待DeepSeek；无编码阻塞。


**目标**：在实际业务调用前持久化含最终答案的唯一提交，恢复时能查准原回执。

**依赖**：M2.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_service.py:confirm_proposal/decide_proposal；gateway.invoke；ARCH D2/D3；新RunItem。

**允许修改**：app/business_assistant_service.py 确认路径；app/assistant_runtime_receipts.py新增冻结与摘要helper（不做恢复）；必要schema内部类型。外部测试和本项实施记录为共同允许项。

**禁止修改**：不新增确认HTTP路由，不把模型文本确认当点击，不改变原业务事务/幂等守卫，不伪称两数据库事务原子。

**实施步骤**：

1. 先验证员工、卡digest/状态/期限/版本及全部答案，得到实际operation/path/query/body；按M2.1保留请求号。
2. 原Proposal→executing与唯一confirmation RunItem/submission_snapshot/submission_digest同事务commit；legacy也创建confirmation但run_id可null。
3. 提交原API必须使用刚冻结的相同规范化参数；禁止调用前重生成请求号或重新从可变草稿取body。
4. 原API结果返回后在独立助手事务记录已确认结果；超时/中断保持executing/uncertain并显示需核对，绝不立即再发POST。

**状态转移**：Proposal pending→executing（冻结成功）→原有success/failure状态；无法确认写结果→uncertain；取消沿原cancel并不算成功。

**异常路径**：冻结commit失败不得调用业务；业务commit后助手commit失败不得报告已回滚；已有冻结摘要不同返回409。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_4.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.4
```

**验收条件**：

- [ ] 补填实际值与冻结值/调用值逐字段相等。
- [ ] 并发双点击最多一次调用；两个业务提交边界故障均有明确结果。
- [ ] 旧无快照uncertain记录不可伪造最终提交；原批量继续执行语义保持原样。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-5"></a>

## M2.5 跨 Run 的准备幂等及完整批量行

**状态**：implemented

**验证状态**：deferred_to_deepseek；本项仅实现服务端稳定来源、完整输入行与准备保存，后台调度/授权接入仍由后续里程碑实现。

**全局顺序前置**：M2.4 done。

**执行记录**：实现日期=2026-09-28；新增assistant_runtime_runner的accept_complete_input/prepare_rows/prepare_work_item及内部RowResolution/ReprepareAuthorization；service.build_proposal/persist_preparation接可选source_work_item_id。首次完整输入在内部prepare_inputs RunItem保存全部UUID行ID、固定顺序、输入摘要与逐行结果，Session/Step乐观版本保护跨Run首次分配。解析读取与无网络保存分开，helper仅flush不commit；显式execution_authorized默认为False，调用方须在同事务完成实际principal/fence/目标授权，M3/M4接入前无后台入口。WorkItem键与规范摘要先核对，卡与来源同事务，只有首次新卡生成原request_id；显式号与服务器生成号严格区分，两个等值输入行不合并。实际容量及本次预算耗尽保留完整pending行，复用不占额度；首次新卡用会话CAS保护跨manifest容量。自然过期按真实期限派生，旧卡保留；显式选中失败/取消/过期行才换intent并supersedes；旧兼容单卡可重准备且不补造历史WorkItem。多轮独立审阅修正了过期无法重开、预算饥饿、混合批量/无卡行永久阻塞、历史goal_version误挡、缓存uncertain与真实结果不一致等问题。AST解析退出0，新文件与service无U+FFFD；未导入app、执行DB/测试/模型。SHA256：runner=`6f9691c098521853c6f090147c4d2dbc025a74744526ba3f39236198f1f43dec`；service=`16d91ec38788fb39e3630de1bf3a008f4d0248fb1effe54b72280f504cd02df1`。并发/崩溃恢复、全部资源边界、旧接口兼容、权限及实际准备事务均待DeepSeek；无编码阻塞。

**后续衔接合同（M3.3/M4.5及事项投影必须沿用）**：prepare_inputs是内部完整行manifest，不是可派发模型工具；实际tool/batch_row沿manifest及原input_item_id恢复。混合批量换版仍保留全部行：未选且已有真实卡的行通过carry_forward保留原WorkItem/Proposal（不克隆成功项、不改旧卡归属），选中行新建意图；未选但尚无卡的行保留原输入与缺项结果，继续首次准备，有旧planned项则supersedes。完整行聚合须读取当前manifest逐行真实引用，不能仅以WorkItem.intent_version等于当前值代替完整集合。manifest.goal_version仅留接受时历史；执行核验当前Run/Grant/Plan目标版本，不因新增其他步骤自动重做旧行。source_refs是原候选{field,selection}内部引用，不冒充已核实EvidenceRef。此为既定完整性/成功行不得重做合同的实现，未新增表/状态机/权限协议。


**目标**：每个真实输入行保持一个稳定意图，同Run重试与重启不重复成卡。

**依赖**：M2.4 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：service:prepare_operations；assistant_runtime_models/schemas；M2.3 helper；ARCH C4。

**允许修改**：app/assistant_runtime_runner.py 新增prepare_work_item/prepare_rows；app/business_assistant_service.py 仅接可选稳定来源参数。外部测试和本项实施记录为共同允许项。

**禁止修改**：不按当前卡片数量推断完成，不复用数组下标作ID，不以截短批量提高成功率，不修改原confirm批量行为。

**实施步骤**：

1. 首次完整输入接受时服务端生成input_item_id列表及固定次序；plan模式键包含plan/step/intent_version，即时模式包含request_id。
2. 插入WorkItem与card关联置于同事务；已存在键先比规范参数指纹，相同返回既有卡，不同409。 先读取既有项再首次生成业务request_id，意图摘要不得因每次随机UUID产生假冲突；先resolve全部读取再进入无网络保存事务。
3. 每行独立保留prepared/needs_input/failed等结果引用；只有完整合法JSON才能展开行，不接受半数组。
4. 新意图版本必须来自员工明确重新准备；建立supersedes关系，保留取消/过期旧卡，不自动改旧键重做。

**状态转移**：WorkItem planned→prepared→settled；未知业务执行→uncertain；批量未处理行保留pending信息。

**异常路径**：中途crash后按行ID恢复；取消/过期卡不能因同键重试重新出现；同名员工/车辆仍要求真实候选选择。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_5.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.5
```

**验收条件**：

- [ ] 双worker同意图唯一卡；最后一行崩溃恢复不丢前行/不重复。
- [ ] 大批量超过资源预算显式保留剩余清单，不假报全成。
- [ ] 未授权后台不调用prepare，准备不写原业务。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m2-6"></a>

## M2.6 只读回执解析框架与通用 Flow 回执

**状态**：implemented

**验证状态**：deferred_to_deepseek；本项仅只读回执服务，不接HTTP路由或后台身份。

**全局顺序前置**：M2.5 done。

**执行记录**：实现日期=2026-09-28；assistant_runtime_receipts新增lookup_receipt、固定Flow分派及纯摘要重建。唯一查询输入是当前已授权会话中的Proposal，读取服务器唯一confirmation并复验冻结摘要/归属/来源；无旧快照unsupported，不补造历史。仅支持通用Flow create/action，复用原CreateInput/ActionInput完整model_dump（包含默认values={}）及原request_digest，按冻结门店+真实请求号查询原RequestReceipt，再核actor/digest/action目标Case。原get_case或注入固定GET native_reader重新验可见性，权限变化不输出原单/回执ID；未接专用族unsupported，缺回执not_found，冲突mismatch，原已知成功状态不修改。显式要求单店scope与身份一致，禁聚合/自行设scope；读取前清洁事务与no_autoflush，无flush/commit/POST/助手状态修改。可靠成功证据来自原receipt，receipt无版本故native_version=None，另列当前Case观察版本，不推断支付/交车终态。独立源码审阅无新增阻断；AST退出0、三个lookup helper直接DB写调用扫描为空、无U+FFFD。SHA256 receipts=`908417484a1eed1fba2b867bf11f8433a01d729220de03b540954196fee3a4a0`。未导入app、访问数据库或运行测试；迟到回执、actor/参数冲突、失权、只读指纹与原Flow回归全部待DeepSeek。M3.4须在结果暴露前重验当前login/Grant；M5.1路由先对跨人/跨店ID作原404授权过滤，不能以本helper的inaccessible DTO代替HTTP授权。


**目标**：把原提交结果分为可靠成功、未找到、不支持、失权、摘要不符。

**依赖**：M2.5 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/flow_engine.py:request_digest/prior_request；app/flow_models.py；app/flow_api.py；M2.4冻结；ARCH B1。

**允许修改**：app/assistant_runtime_receipts.py 回执分派/通用flow实现；仅为复用原纯digest helper调整flow_engine导出（行为不变）。外部测试和本项实施记录为共同允许项。

**禁止修改**：不新增自由表名/actor/request_id查询参数，不把PurchaseReceipt/收款明细当命令幂等回执，不尝试POST。

**实施步骤**：

1. 以服务器持有的Proposal及冻结snapshot作为唯一查询入口；先验owner/store/session，再按已登记operation解析回执族。
2. 通用flow create/action严格沿原request_digest规则，核对actor及目标case；读取结果再走原可见性查询。
3. 未接入的专用operation返回unsupported，不能套通用flow摘要；原业务接口已明确成功的结果保留。
4. 本项只提供纯解析/注入只读查询服务；HTTP路由M5.1接，后台身份M3.4接，不提前绕授权。

**状态转移**：确认未知→查询confirmed_success可供后续协调器恢复；not_found/unsupported/inaccessible/mismatch仍未知。

**异常路径**：回执迟到、ID碰撞、同请求号不同actor/参数、原单当前不可见均不标完成。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m2_6.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M2.6
```

**验收条件**：

- [ ] 摘要与原flow实现逐项一致，模型/员工不能任意查他人request_id。
- [ ] 回执查询数据库业务行指纹不变。
- [ ] 缺回执不自动生成新请求号或重试确认。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-1"></a>

## M3.1 统一工具注册与读、准备、计划分层

**状态**：implemented

**验证状态**：deferred_to_deepseek；仅工具注册与兼容分派实现，保留原schema与确认边界。

**全局顺序前置**：M2.6 done。

**执行记录**：编码日期=2026-09-28；新增app/assistant_runtime_registry.py，service仅工具目录/分派及完整调用预校验接线。静态登记原11个legacy+7个business工具，保留原名称、schema、顺序及profile；read/prepare/plan分类不改变MCP annotation或原API能力。完整列表在任何handler前拒绝未知工具、重复ID、截断/重复JSON键及顶层额外参数；MCP单次调用不要求model call ID。legacy只保留原顶层/批量行信封校验，questions及原字段仍按原逐行边界，business仍使用原Pydantic校验。DomainRegistry只有静态容器；受控GET注入仍需M3.4真实身份transport。两方代码审阅无阻断；AST/UTF-8检查正常（无U+FFFD），静态目录18项覆盖一致；最初静态字面量提取因TOOLS使用tool(...)失败，已改为只读AST参数提取，不运行应用。源码SHA256：registry=e059495085db1b92eef34ba884e7971cdb7b6cdcf3f877b119fda69ce8dd116d；service=1a0b1f98244a32ed235b95109b847b2ac97844e91967e34fcbf7bcc34ea1ca0e。测试=deferred_to_deepseek，命令/退出码不适用；待验证全量目录/schema等价、整组非法调用零前序执行、200边界、旧questions/逐行失败、MCP、重复注册和原GET动态权限。未导入app、访问数据库或调用模型。

**集中测试补充（2026-09-28）**：完整基线复跑发现 `registry_for_config(config)` 在历史调用点传 `config=None` 时抛 `AttributeError`（两条原回归因此失败）。已按 M3.1 之前的单一目录语义回退：缺配置时取 `legacy` 而不可能是 `business_v1`，既不误开业务工具面也消除崩溃路径。另：整表预校验被拒时必须在同一轮把拒绝结果作为工具消息交回模型（`business_assistant_service.py`），否则 M3.1 之前"逐调用返回 422 工具结果"的原契约被打断——该修复见 PATCH-M5-5-02 §3。复验：`tests/test_business_assistant_scope.py`、`tests/test_business_assistant_guides.py` 全通过（run `20260928T090316Z-f2eeac2f7b`）。


**目标**：让工具目录和执行分派共享一份已有权限及操作元数据。

**依赖**：M2.6 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：business_assistant_service.py:tools_for_config/run_tools；business_assistant_gateway.py；business_assistant_business_tools.py；business_assistant_capabilities.json。

**允许修改**：新增 app/assistant_runtime_registry.py；service仅分派适配；原business tools仅复用必要导出。外部测试和本项实施记录为共同允许项。

**禁止修改**：不重建已废止动作名白名单，不扩充未评审写能力、不把管理封闭面开放为模型工具、不提供confirm/Grant工具。 本项保持旧schema，M3.3按已冻结合同兼容新增v2字段。

**实施步骤**：

1. 给现有工具登记kind=read/prepare/plan及handler/schema，保留对外旧工具名和参数；禁任意插件加载。
2. 原业务operation仍从reviewed目录及原OpenAPI解析，role_may_read继续生效；prepare仍不写业务。
3. 将完整工具call校验放在registry入口，重复tool ID、未知工具、额外身份参数拒绝。
4. 提供DomainAdapter静态注册容器及受控native_reader注入位置，未注册对象明确unsupported。

**状态转移**：工具请求→已校验意图→受控handler；不完整/非法请求无RunItem可执行项。

**异常路径**：模型返回confirm/SQL/shell/URL或未知工具均失败可解释；不得降级到通用eval/invoke。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_1.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.1
```

**验收条件**：

- [ ] 旧工具目录与193能力映射未丢项。
- [ ] read/prepare/plan均不能取得业务确认或授权写能力。
- [ ] 工具schema与handler一一对应，重复注册启动检查失败。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-2"></a>

## M3.2 对象引用分派及通用 Case 快照

**状态**：implemented

**验证状态**：deferred_to_deepseek；仅对象读取、固定结果提取与快照实现。

**同日重开原因**：M3.3末审对照M7共同合同，发现默认领域注册仍直接写在registry工厂，而M7明确只在domains/__init__.py逐项接入。按本项原允许范围将注册收口至该静态入口，不改变工具/业务能力；原指纹保留，修后另记。

**第二次重开原因**：ARCH B1及M7.4.1/M7.4.3要求多个provider共用Case类型及实际kind/version、按不同事实键分派。原注册仅有对象selector，无法表达事实子provider的适用范围；在本项registry注册范围内分离事实适用元数据与唯一对象selector，保持exact fact key唯一，不新增业务能力。

**第二次修正结果**：registry新增静态fact_kind_versions及supports_fact；Case事实必须匹配经原GET证明的kind/version，事实适用元数据不占唯一对象selector，不改变现有flow_case注册。root与作者源码审阅、AST/UTF-8正常，SHA256=8e38bb1a8f66a3d6868787c376dd28e12453bb75c3ebb3770e8080790eb75730。共享Case事实及重复注册运行验证仍后移，恢复M3.3接线。

**重开修正结果**：静态登记已移至domains/__init__.register_adapters，registry懒调用后seal，Case provider及操作值未变；两方源码复审无循环初始化问题，AST/UTF-8正常。修后SHA256：registry=167bf6903ec3cbd9939521c8c505ab9336c6f4c53b5f904e3853fc83f197b9cf；domains/__init__=43ab25ec709d8a8d93e592bde654aea6f2a06ba88636f64893537a8e3a5fab11。没有测试或运行导入，恢复M3.3。

**全局顺序前置**：M3.1 done。

**执行记录**：编码日期=2026-09-28；新增app/assistant_runtime_objects.py、assistant_runtime_domains/__init__.py与flow_case.py，registry登记唯一通用case fallback及固定GET/create/action结果provider。read_object先经原GET取得真实kind/flow_version再选择专用provider；DTO校验对象ID一致。通用快照只读取实际Case/任务/动作，明确布尔enabled才证明可用，未提供版本为null、任务done_by/done_at为空，原观察UTC随证据保存。原FLOW_CATALOGUES证明版本后复用原导航，否则case/{id}；仅七个原导航关联键参与跳转，不递归提取证据。resolve_result为内部绑定结果resolved/unbound/unsupported，缺ID不改变原命令成功、不重放。跨店/不可见404、原409保留，截断/缺tasks/actions不伪空成功；无领域事实provider时返回未知。两方源码审阅及修正复审无阻断，四文件AST及UTF-8无U+FFFD。SHA256：objects=b46bbf73724c84d0da201b6f91318ac60e4eb1dabc02cad98b81388e36db04a6；registry=a7e282bb4ad20e7e53bf333c2659da5bbd1d9015bd1590694ff1b5add4e98ffa；domains/__init__=2d788430f3665d09766dd15ef36a7c418376d479353ec0a364ed0bbd77b1d731；flow_case=3ce29b02ea955fee39654baa19e1136761009711654536f0cc035fcc52e13f24。测试=deferred_to_deepseek，命令/退出码不适用；待测跨店/撤权/旧版本/畸形与截断响应/任务ID误绑定/固定结果提取/真实原接口。没有导入app或访问数据库；实时principal重验须M3.4受控transport接入，当前不宣称Runtime已可执行。


**目标**：用真实Case读取建立通用对象/任务/动作/人工入口映射，供随后计划和条件使用。

**依赖**：M3.1 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/flow_api.py；app/flow_engine.py；app/business_assistant_case_tools.py；app/business_assistant_workboard.py；web原路由映射。

**允许修改**：新增 app/assistant_runtime_objects.py、app/assistant_runtime_domains/__init__.py、flow_case.py；registry注册。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改原流程定义、不猜专用单据id含义、不把原case data任意字段递归当证据。

**实施步骤**：

1. 实现read_object/resolve_result，ObjectRef类型严格注册；通用Case的type固定case，flow_case.py是文件名，用原授权GET及flow_version；专用adapter按已证明kind/固定operation或fact前缀分派。
2. 动作字符串映射unknown，明确enabled/disabled才保留确证；tasks引用原真实任务。
3. 按确定operation及response形状提取新case_id，缺ID返回显式无法绑定；未知版本返回原通用页。
4. 快照加入观察时间、原版本与来源引用；禁止从模型总结覆盖快照字段。

**状态转移**：读取成功产生快照，不改变原单；不可见404；未知动作availability=unknown。

**异常路径**：跨店ID、已删除关联、旧flow版本、权限变化、分页未找到分别展示准确原因。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_2.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.2
```

**验收条件**：

- [ ] 对象ID/类型/版本与原API一致；不误把任务ID当case_id。
- [ ] 所有读取经过原权限；没有版本时null。
- [ ] 快照与model文本冲突以原事实为准。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-3"></a>

## M3.3 持久 DAG、旧计划兼容与结构版本

**状态**：implemented

**验证状态**：deferred_to_deepseek；实现持久DAG、兼容投影及结构变化失效处理，保留原验收。

**前置修复历史**：主体实现后因M3.2注册扩展接线临时blocked；该项已按原范围修复并复审，本项恢复通用对象分派，未新增领域适配器。

**全局顺序前置**：M3.2 done。

**执行记录**：编码日期=2026-09-28；新增assistant_runtime_plans.py，workboard作v1/v2分派与真实行投影，business_tools新增有限v2字段并保持默认v1原JSON形状，service/prompt仅默认关闭开关下加入v2说明。实现稳定DAG、原引用授权核对、旧计划显式升级保留历史、会话/计划/步骤并发守卫及失败整体回滚。结构变更加goal_version并暂停Grant/停止关联旧Run，真实关系回填只加version；已冻结、已办理或未知历史不能通过编辑重绑/删除/重办。完整manifest投影保留carry成功原卡、无卡行与逐行异常，排除superseded历史，不按WorkItem当前版本误删行；卡成功不表示事实完成。通用引用只走已注册adapter，Case事实按原kind/version与精确fact_key适用元数据核对；非Case懒接M3.4同步身份工厂。作者/root/独立代理源码审阅完成，AST退出0、UTF-8无U+FFFD；没有导入app、访问DB或运行测试。报告=docs/implementation-checkpoints/CP-06-v1.md。SHA256：plans=81991e29f3f6b59248fa63bb9dfb98dfea83127d043db03a296621a4c6b0e606；business_tools=fba1bb33eddb85bd59c3760d61674f88c4a0f67df3eab51968fcd99ef223825b；service=27e92c34bb114eb90489fd44dc82c5cb3c89a793643ab90a2db29f048b76151f；workboard=c55aa03ef54367c2e402cb2ceaa034c2f07088a311019cebaa8c9bbfc3a54aa5；prompt=e9e77af7afe59b37c43f5d69fd5c32a9d7fc8d8f4a651aafb5519b12993bed61。测试=deferred_to_deepseek；原升级/DAG/并发/权限/历史保护/完整批量/v1兼容验收全保留。后续M3.4实现principal_for_request(db,request,user,session_id)，M3.6求值typed条件及纯读完成依据；当前不宣称持续跟进可执行。


**目标**：让新计划可安全保存依赖图，旧计划原样读；所有结构变化具备明确版本。

**依赖**：M3.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/business_assistant_workboard.py:save_plan/validate_graph/derive_steps/plan_briefs；新PlanStep/WorkItem；ARCH C2/D1。

**允许修改**：新增 app/assistant_runtime_plans.py；原workboard仅兼容分派和投影；service plan工具接线；business_assistant_business_tools.py WorkPlan/WorkStep仅新增ARCH F规定的可选v2字段；business_assistant_prompt.py仅v2工具说明。外部测试和本项实施记录为共同允许项。

**禁止修改**：不把旧steps与新表双写为两份真相，不自动授权旧计划，不允许改已冻结确认参数。

**实施步骤**：

1. 实现save_plan(expected_version)、validate_dag、project_legacy_plan；禁止环、悬空、跨plan/跨店/他人卡关联。
2. 旧engine=1只读原steps；员工明确编辑/升级才事务性转为v2 PlanStep，旧steps保留历史。升级保留原title/wait_for及真实proposal_id，旧卡source_work_item_id仍null。
3. 真实前单ID/状态推进只加version；目标/必要步骤/条件结构变更加goal_version并暂停Grant/取消过时Run。
4. 必要完成条件与准备条件分开；空完成条件不自动完成。Step.proposal_id只作旧/单卡兼容，新批量按当前intent版本WorkItem完整集合聚合，PlanStepView返回proposal_ids；历史superseded项不能误判损坏。步骤绑定已成功卡不可随意清空或降为未执行；failed/cancelled仅员工明确新intent可重开，uncertain不可绕核对。
5. 实现schema_version=1/2兼容合同；v2使用typed conditions，保留title/wait_for为说明。旧请求默认1，无条件时不自动升级/跟进；不从自由文字猜条件。

**状态转移**：Plan active/paused/completed/cancelled；Step按ARCH D1；前序未证实→waiting；缺员工事实→needs_input。

**异常路径**：同版本并发保存409；取消前序阻塞后序；新增必要工作不能偷偷加到既有已授权范围。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_3.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.3
```

**验收条件**：

- [ ] legacy计划无需新授权可正常查看；v2无双写漂移。
- [ ] 循环/跨店/重复key/过期expected_version均拒绝。
- [ ] 结构变更暂停授权，单纯真实ID回填不会反复要求重新开跟进。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-4"></a>

## M3.4 可信内部身份与原授权 GET transport

**状态**：implemented

**验证状态**：deferred_to_deepseek；当前实现身份工厂、授权重验及原GET内部transport，原验收保留。

**全局顺序前置**：M3.3 done。

**执行记录**：编码日期=2026-09-28；新增assistant_runtime_principal.py，security仅get_user前3行私有分支，gateway仅内部GET及原invoke分派。提供同步principal_for_request、principal_for_run、revalidate_principal、request_for_principal、native_reader_for_principal；冻结真实actor/store/role/access及login或Run/Grant来源、源Engine，隐藏login引用。独立同Engine短读会话核已提交授权，避免PG REPEATABLE READ/ORM缓存沿用旧权限，不commit/rollback调用者；Connection bind及活动共享连接池无法保证独立时明确拒绝，不将内存库改为磁盘。真实Run检查running/lease/fence/stop、Plan范围和目标版本，Grant检查状态/期限/原权限快照；不绑定易变Run.version、不修改旧会话权限。私有Python能力绑定确切GET/路径/查询，目标路由前核同Engine，仍走原get_user/attach_scope/业务守卫及完整Host中间件；禁Cookie混用、POST、重定向、任意URL，来源/结果前均复核。默认关闭开关即时阻止新Runtime/Grant读取，普通无marker登录路径原文保留。作者/root/独立代理源码审阅，3文件AST退出0、UTF-8无U+FFFD。SHA256：principal=f28d22db68c4491b0e86aa3aed4d44c9eae625ba4f217bf049e9bcb85d5069e5；security=cc1692f8d98033a695876a35522f43548ce6ef3ccbc0cff94fed9ccda709a832；gateway=2bbbe7cab8331e21043da2e18bbcf771458f0716447d4f6dff3d72ed86e96aa8。测试=deferred_to_deepseek；原岗位/门店、伪造标记/头、注销/到期/撤权、同库连接、PG快照、Host及原Cookie回归均待集中验证。未导入app、访问DB、测试或启用后台。M3.5负责失效控制落库；M4接完整工具/模型外发/写回边界及事务fence CAS，本项提供守卫，不宣称这些调用点已接完。


**目标**：让后台以原员工当前门店权限读取，并在每次动作/外发前复核授权。

**依赖**：M3.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/security.py:get_user；app/tenancy.py；app/user_access_service.py；app/business_assistant_gateway.py:invoke；ARCH E1。

**允许修改**：新增 app/assistant_runtime_principal.py；security仅私有内部身份分支；gateway增加内部GET transport接线。外部测试和本项实施记录为共同允许项。

**禁止修改**：不修改RBAC表/岗位门店判断，不接受网络身份headers，不全局dependency_overrides，不以管理员令牌代跑。

**实施步骤**：

1. RuntimePrincipal必须服务端查User/当前门店岗位/access_version；来源只允许原登录session或有效Grant。
2. 使用模块私有Python标记注入ASGI scope；普通网络请求永不产生该对象，原Cookie/CSRF路径保持。
3. transport仅允许registry受审GET operation，原路由再次get_user/attach_scope/业务权限；不接受任意URL/方法。
4. 每工具前、模型外发前、结果暴露前重验；提供可注入clock与只读客户端测试，不持久Cookie。

**状态转移**：即时login源注销/到期→Run停止；Grant源注销可继续，撤权/停店/改岗位/必须改密→Grant失效且Run停止。

**异常路径**：跨店请求、旧access_version、伪X-Run-ID、内部GET包装POST、授权检查时网络失败全部拒绝。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_4.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.4
```

**验收条件**：

- [ ] 原岗位矩阵及门店范围一致，集团仍只读。
- [ ] HTTP伪造所有身份头不能进入内部分支。
- [ ] 退出后只允许有效Grant继续；旧session/proposal快照没有被覆盖。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-5"></a>

## M3.5 逐事授权、暂停恢复与结束

**状态**：implemented

**重开记录**：M3.6前置审阅发现合法login Run在同goal事项已有active Grant时，被current_scope误判为旧范围而无法完成Plan。仅修close_followup_control两处当前范围判断：严格完成授权通过的login Run可结束当前goal；grant Run仍要求自身Grant匹配，permission_changed不放宽。M3.6暂记blocked，两作者已暂停写入；验收条件不变。

**重开收尾**：两处current_scope已同样修正，原strict完成授权/active目标/Step证据、版本锁、lease/fence和提交前守卫全部保留。root与独立代理窄审无剩余阻断，AST/UTF-8正常；plans本轮最终SHA=fcc2f94c3fe42802babb37c7b698412c1147141baa27fd0ecb53309ba968705b，替代下方本项初次收尾指纹。未运行测试，恢复M3.6编码。

**验证状态**：deferred_to_deepseek；显式授权服务和同事务唤醒事件原语已编码及源码审阅，原验收保留。

**全局顺序前置**：M3.4 done。

**执行记录**：编码日期=2026-09-28；plans增加本人POST/CSRF/expected_version的enable/pause/resume/revoke、独立失效清理和worker控制收尾；principal增加真实登录授权工厂及控制守卫；新增outbox只写同事务来源唯一事件，无dispatcher。Session→Plan锁与版本守卫，唯一active Grant，目标变化/过期显式新授权并保留旧历史，退出不撤Grant；暂停/结束仅停止后续执行，原卡及业务结果保留。过期授权展示与恢复一致；提交后失权不返回旧私有视图，明确授权变更已记录。无Run清理只接受fresh权限/到期证据，不接受caller失效理由；旧goal不能停止新Grant。worker完成要求active当前goal、严格stop=false权限和既有证据，失权控制只允许本Run有效lease/fence；Run强制本事务版本CAS，条件真实求值由M3.6接续。emit_wake_event校验同店来源/引用、规范化幂等及savepoint并发冲突，不commit调用者；同key不同事实409，重复不重置分发进度。作者/root/独立代理源码审阅修复暂停越级完成、已停止Run推进及CAS边界；3文件AST退出0、UTF-8无U+FFFD。SHA256：plans=df821186cab3038d786dbb48de18ccebc6e2be917fde257ea79ec735f276ccd5；principal=4d81cede4872eab19ac895d6ca29e1cbc8ac7147b6f70ec860488211ba6785fe；outbox=cb8fda84daae8e401bc3a24db6b4521dce84ca03dd368886c34b31a35469c69b。测试=deferred_to_deepseek；原并发唯一/CSRF/幂等/退出与撤权/期限/目标变更/同事务回滚/lease-fence与PG/SQLite检查均待集中验证。未导入app、访问DB、运行测试或启用后台。


**目标**：以员工明确点击保存长期查询/准备授权，并随目标和当前权限管理生命周期。

**依赖**：M3.4 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：assistant_runtime_plans/principal/models；原session权限规则；ARCH D/E/F。

**允许修改**：app/assistant_runtime_plans.py 增加followup_transition；principal复核；暂不加前端；新增 assistant_runtime_outbox.py 仅emit_wake_event(db,...) add/flush/来源唯一处理，无dispatcher。外部测试和本项实施记录为共同允许项。

**禁止修改**：不允许模型/MCP启用授权，不将退出登录等同撤销，不由GET创建Grant，不自动复活revoked。

**实施步骤**：

1. 实现enable/pause/resume/revoke服务，必需本人计划expected_version；服务返回PlanView allowed_actions。
2. enable绑定owner/store/role/access_version/goal_version；同plan唯一active；expires_at默认为null。
3. pause设置Plan paused/Grant paused并对关联Run stop_requested；同goal_version且权限未变的resume可恢复原Grant；goal_version改变的resume须员工明确重审范围，原Grant revoked并新建绑定新范围Grant，同事务保存历史。
4. 目标完成/员工结束/权限失效撤销；相关状态及WakeEvent同事务，但此时只写事件不启动worker。 本项先实现共享emit_wake_event原语，M4.7复用，禁止先直接插表再设计第二套。

**状态转移**：active↔paused；active/paused→revoked；Plan结束→cancelled且停止后续查询准备，原卡/已执行业务不回滚。

**异常路径**：旧版本409；他人/跨店404；无效角色403；没有新授权不能因新消息自动恢复。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_5.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.5
```

**验收条件**：

- [ ] 点击幂等且并发只能一个active；默认不开启。
- [ ] 退出不撤Grant，撤权立即使其无效。
- [ ] 暂停/结束停止新增卡，已有草稿/确认结果保留。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m3-6"></a>

## M3.6 有限等待条件与真实完成判断

**状态**：implemented

**前置修复历史**：M3.5登录Run与active Grant并存的完成分支已单独修复审阅后恢复本项。暂停时conditions存在未完成草稿，plans尚未写入本项改动；未把草稿记为实现完成。

**验证状态**：deferred_to_deepseek；条件读取、结果和步骤持久化已编码及源码审阅，原验收保留。

**全局顺序前置**：M3.5 done。

**执行记录**：编码日期=2026-09-28；新增assistant_runtime_conditions.py，plans接逐步骤求值/写回/真实完成证明。五类typed AND返回satisfied/unknown/reason/evidence/fingerprint；原授权GET重读，任务取原Case返回字段，Proposal只认原succeeded/2xx及实际冻结确认，原结果data缺失不伪造失败；未知回执等待后续协调器。事实键须已注册且适用原kind/version，有实际证据；空完成条件、仅动作可办/到时/任务未完成不能完成业务。有限明确日期/时分及今天/明天/后天按原员工消息日期和应用时区核对，UTC保存；歧义/DST缺口/缺来源列needs_input，不声称任意自然语言时间均支持。纯读要求完整当前read WorkItem集合、最新成功RunItem、当前scope/goal/intent及原GET重读，并在await后再次核对来源；父Run后续停止不抹去已成功子项。指纹规范条件/任务/动作/证据排序，排除Runtime观察时间，包含原业务数据、真实完整行状态、意图和目标版本；普通求值回写/租约心跳不制造变化。evaluate_plan_conditions完成全部读取和双快照后签发仅内存令牌，apply_condition_results短事务校验Session/Plan/Step/来源版本及Run lease/fence/stop，真实版本查询刷新identity-map；只写步骤及必要版本。完成必须本Run一次性60秒内的已提交proof，旧last_evidence不能单独结案；已完成步骤遇反证/失权/暂不可读保留历史并投影待复验，阻依赖且不自动重准备。提供同步server-only on_plan_updated(db,principal,plan_id,version)同事务事件hook，默认None；异常整体回滚，后续M4固定appender不得commit/网络/携带私有内容。作者/root/独立代理源码审阅及hook窄审无剩余阻断；AST退出0、UTF-8无U+FFFD。SHA256：conditions=b4343987fce240147505dbc9dfc5c4f797b4d07d2e80c53a3c3bd1c9f74c22ad；plans=19d00e7b5c012472ce6859b4d7f1f7f786dcef9c972d03720c48af7d3e92050f。报告=docs/implementation-checkpoints/CP-07-v1.md；测试=deferred_to_deepseek。原AND/assignee/时间/取消/unknown、真实事实更正、指纹、整批行、纯读、并发/权限/fence、事务回滚及原接口回归全部待测；无app导入、DB访问、测试、迁移或模型调用。M4须接已认领且真实绑定Plan/goal的Run、固定原GET、同事务事件和安全工具边界；本项不代表worker或持续跟进已可运行。


**目标**：用可审计事实决定能否准备下一步及是否真正完成。

**依赖**：M3.5 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：assistant_runtime_objects/plans/principal；原flow任务读取；ARCH E4。

**允许修改**：新增 app/assistant_runtime_conditions.py；plans仅调用条件结果更新step。外部测试和本项实施记录为共同允许项。

**禁止修改**：不执行模型表达式、不以任务数为资金/库存完成、不读取不授权对象，不新增原业务状态守卫。

**实施步骤**：

1. 实现五种条件AND求值并返回satisfied/unknown/reason/evidence/fingerprint；每个对象按最新原GET重读。
2. proposal_succeeded仅原已确认结果；native_action_available仅enabled；任务状态及assignee按原字段；fact_key必须adapter登记。
3. due_at必须有原消息来源并以UTC存储、门店时区显示；没有明确时间则needs_input。
4. 前置与完成分开，未知/取消/回执未核对阻塞依赖；空completion_conditions不能用all([])完成业务，缺依据列为needs_input；纯读完成依当前read WorkItem，不冒充业务完成。固定排序生成事实指纹用于零变化不调用模型。

**状态转移**：waiting→可准备仅在全部条件确证；unknown保持waiting/needs_input；completed只在所有必要完成条件确证。

**异常路径**：动作字符串unknown、原单失权、时区边界、事实被更正/过期、重复证据不造成提前完成。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m3_6.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M3.6
```

**验收条件**：

- [ ] AND/未知/时间/取消/不同assignee边界均覆盖。
- [ ] 同事实相同指纹；变化后强制重读而非旧摘要。
- [ ] 未查询到付款/实物/签回事实不能完成相关步骤。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-1"></a>

## M4.1 Run 入队、CAS领取、租约与取消

**状态**：implemented

**验证状态**：deferred_to_deepseek；队列、租约与原会话忙标记协调已编码及源码审阅，原并发和故障验收全部保留。

**全局顺序前置**：M3.6 done。

**执行记录**：编码日期=2026-09-28；新增app/assistant_runtime_queue.py，service/API原六处会话忙操作仅抽共享CAS，保留原对话/MCP时长及返回合同。用户Message与Run同事务、摘要覆盖全部原输入；同键竞争回滚后按真实digest重读，后台signal/manual不伪造消息。固定全库slot=1，PG首SQL表锁NOWAIT、SQLite首SQL零行UPDATE取得写保留，再Session→Plan→Run短事务CAS；claim/reclaim使用独立新Session，worker先回收再领取。租约90秒/心跳20秒，稳定runtime:RunUUID忙token与同事务Run源身份/lease/fence/stop/goal守卫配合；续租不增Session语义版本，原MCP仍受忙标记保护。失效queued最小取消避免队首饥饿；running先stop、安全边界收尾；失租回收只改助手记录，30/120/600有限退避核完整manifest、真实WorkItem/Proposal及run_id为空的确认记录，不重试confirmation或未知结果。公开lock_for_write无commit、拒脏状态、锁后重验并设置写阶段标记；调用者须全部GET先完成、成果flush后再验权提交。bind_run_plan只接受该Run实际保存的Plan，保留原request_digest并重签principal。release的同步before_finish仅严格succeeded/failed路径，用于后续最终安全回复与Run同事务；控制取消禁内容hook。Plan完成已stop自身Run时仅cancelled控制收尾，不把Run状态当业务完成。作者/root及两独立代理源码审阅修复了释放冲突静默遗留busy、入队竞争、失效队首、registry接口、完整批量重试关联及写事务守卫；AST/UTF-8/本地导入符号静态核对退出0，无U+FFFD，没有导入app、访问DB或执行测试。SHA256：queue=5c33dcde6ec7324ec5faed500bdd6064a6295b81ee19efe02f1d5aefb49b7bc2；service=163f31af23296ea55750a2d89a0aae58a5b08087ef276ec2ff95fbd12516830d；api=a16e3d4e361edd8b2c74a53330da89cdb71a5fea7564c3208aae1fc6354a685b。测试=deferred_to_deepseek；双进程领取/PG隔离与NOWAIT/SQLite busy/过期晚返回/权限失效/MCP/批量重试及hook原子性仍待集中验证。事件/worker/HTTP接线在后续项，不宣称后台已可运行；无编码阻塞。


**目标**：跨进程只让有效worker处理同一会话/计划，重复请求只生成一个Run。

**依赖**：M3.6 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：assistant_runtime_models/principal/plans；service:busy_lease_seconds；business_assistant_api.py MCP busy_token；ARCH E2。

**允许修改**：新增 app/assistant_runtime_queue.py；原session忙标记操作仅抽取共享CAS helper。外部测试和本项实施记录为共同允许项。

**禁止修改**：不引入Redis/Celery，不用进程内锁作为唯一并发保证，不持事务等模型，不破坏MCP已有忙租约。

**实施步骤**：

1. enqueue_run先验权限/输入摘要，以owner/store/trigger_key唯一入队；相同request_id不同正文409。 用户Message与Run同事务保存，摘要覆盖content/thinking/plan_id/entry_context；后台Run无伪user消息。
2. claim_next按session→plan→run顺序短事务CAS，检查busy_token/目标版本/slot；设置lease_owner、lease_until、递增fence。
3. 实现heartbeat/release/cancel/reclaim；90秒租约20秒续租；任何写回校验fence、有效授权、stop_requested及goal_version。
4. queued可直接cancelled；running请求停止后在完整工具安全边界退出；当前有效fence允许stop=true时只做cancelled/skipped/释放本人busy的控制收尾，不得新准备；失租worker连控制收尾也不能覆盖新持有者。安全读/准备失败按30/120/600退避，confirmation永不入队重试。

**状态转移**：queued→running→终态；安全失租→queued；queued→cancelled；旧fence失效后不得写回。

**异常路径**：双worker、SQLite busy、MCP占用、时钟推进、重启失租、暂停时晚返回均处理，不拿新request_id重放。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_1.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.1
```

**验收条件**：

- [ ] 两个独立DB连接/进程竞争唯一领取，卡片写回也受fence保护。
- [ ] 取消queued无需假执行；安全重试次数有限。
- [ ] 过期worker不能清理新worker的busy_token。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-2"></a>

## M4.2 持久事件序号、展示快照与补读

**状态**：implemented

**验证状态**：deferred_to_deepseek；同事务事件、完整展示快照及授权补读已编码及源码审阅，原验收保留。

**全局顺序前置**：M4.1 done。

**执行记录**：编码日期=2026-09-28；新增app/assistant_runtime_events.py，queue仅在真实入队/领取/重排队/终态处轻接事件，并在fence CAS后绑定本事务事件能力。固定Run Core CAS同事务递增version/event_seq并插入严格RunEventView；queue生命周期核原已提交状态，不为心跳、仅stop、幂等返回或绑定Plan伪造完成。worker普通事件只接受tool/Proposal/Plan的实际关联引用；能力绑定原principal/Session事务/fence，终态收尾能力仅可final展示。progress接完整累计文本，跨片认证标签保留在调用者内存、文本脱敏后保存完整display/revision，非final最多每秒一次、final立即保存；provider字典/原reasoning不进入事件。before_finish先最终reply/display，queue后追加terminal，调用者末尾fresh授权同事务提交；未持久的中间片段不能声称崩溃后可恢复。固定append_plan_updated兼容M3现有同步hook，验证实际Plan版本和已CAS Run；失权控制只保存plan_id。read_events由当前真实登录先授权本人同店父Run，再按after_seq升序补读，返回前复验；不借已结束worker身份读历史，后续SSE每次缓存yield前仍须重验。作者/root及独立代理分项审阅无剩余明确阻断；修复中文紧邻Cookie/CSRF等标签漏清，未改原service/stream。AST/UTF-8/本地导入符号静态核对退出0，无U+FFFD；未导入app、访问DB、执行测试或启用功能。SHA256：events=ad4925c0a862dc1c9c0fee6fd7acf5d93cfcf2df72fdeb1ed5b1b96cb4ba9d4e；queue=c1d5265d74ea63287b38ab8e88eb35bbedfa2e2338bb9b73804fabb9d6ea6c3d。测试=deferred_to_deepseek；并发序号/回滚、失租与跨事务能力、原业务已成功但事件失败、1秒合并/终态全文/分片凭据和中途撤权补读均待集中验证。没有HTTP/SSE或worker实际运行验收，后续项继续接线；无编码阻塞。


**目标**：页面重连能从真实数据库状态恢复进度，不丢事件也不编造完成。

**依赖**：M4.1 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：新Run/RunEvent；service:scrub/safe_text；原SSE SafeDeltas；ARCH F。

**允许修改**：新增 app/assistant_runtime_events.py；queue状态提交处轻量接入。外部测试和本项实施记录为共同允许项。

**禁止修改**：不存reasoning、原工具密钥、Cookie、客户全量payload，不每token创建一条事件，不用内存序号。

**实施步骤**：

1. append_event在同事务原子增加Run.event_seq并插入RunEvent；所有事件先按schema脱敏。
2. progress保存安全display_text完整快照及revision，最多1秒合并一次；结尾立即flush最终快照。
3. read_events按after_seq有序返回；未知/越权Run拒绝；实际状态变更才产生terminal事件。
4. event与对应card/plan状态使用调用方同事务；通知事件不在此引入另一套协议。

**状态转移**：seq严格递增；重读同seq客户端可去重；断流不改变Run。

**异常路径**：事件写失败整体回滚对应Runtime变更；原业务确认已成功不能被事件失败改成业务失败。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_2.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.2
```

**验收条件**：

- [ ] 并发event序号唯一且无乱序暴露；从任意seq补读可还原最终display。
- [ ] 日志/事件未持久原推理与认证值。
- [ ] 旧数据无event不会伪造执行已完成。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-3"></a>

## M4.3 有来源上下文快照与预算

**状态**：implemented

**验证状态**：deferred_to_deepseek；有来源快照与上下文预算已编码及源码审阅，原验收保留。

**全局顺序前置**：M4.2 done。

**执行记录**：编码日期=2026-09-28；新增app/assistant_runtime_context.py，service只加build_runtime_context薄包装，prompt只补Runtime来源字段合同，原_conversation未提前接新写入。已领取Run按真实请求消息或后台入队时刻锚定；固定顺序组装并重新调用原授权GET。绑定Plan卡片/明确对象选择/快照指针按真实目标隔离，完整manifest保留全部未处理输入及合法carry。追加snapshot引用真实through_message_id，旧问答、候选、单位与已发送文件文本保留为未核实资料；无自动文件读取或摘要模型。30条/24000字符只限最近原文窗，来源摘录另计显式可信provider总预算，默认None不猜容量；超限needs_input，不截当前输入、完整工具JSON或批量行。快照幂等只忽略observed_at，保留来源/native_version；保存先读后短事务，fence及Session/Plan版本复核、flush后重验授权，返回同步实际新Plan.version。作者/root及独立代理修复旧目标选择混入、完整批量缺失、旧候选丢失、整会话永久24k阻塞、证据误复用及自己写回导致版本冲突，终审无剩余明确阻断。AST/UTF-8/本地导入符号静态核对退出0、无U+FFFD；未导入app、访问DB、执行测试/迁移/模型。SHA256：context=eedcbf1218e05762ed9dc2d2148488a238eddc18e745fef335d99fefc94239a7；service=2b2b80f2a51cc8e42c5fb075f81a4718a853c36d0e0cc0de4797ef3bb14b09f4；prompt=2b22abec86a916acc22d1fdc8d1c02fe3f343efba63c39723739aae027aab777。测试=deferred_to_deepseek，长对话/消息排队/完整批行/脱敏JSON/跨目标与撤权/快照并发和回滚/实际预算全部待测；当前是完整来源摘录，无语义压缩，不宣称worker已可运行。详见CP-08-v1；无编码阻塞。


**目标**：长对话和恢复保留目标、明确选择与待解决项，每个事实能回到原来源。

**依赖**：M4.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：service:_conversation/prompt_for_config；business_assistant_prompt.py；新ContextSnapshot；原files流程；ARCH G。

**允许修改**：新增 app/assistant_runtime_context.py；service仅调用context builder；原prompt仅必要字段说明。外部测试和本项实施记录为共同允许项。

**禁止修改**：不引入向量库/跨人记忆，不把文件解析当证据，不自动读取文件/URL，不保存原推理或删除旧消息。

**实施步骤**：

1. 按ARCH G顺序组装context；最新输入和完整工具JSON优先，不能静默截断。
2. 超过原30消息/24000字符历史窗前生成只追加snapshot，through_message_id固定；已确认选择保留原message/object引用。
3. 区分verified facts与unverified notes；资金/库存/签回等只能由原API事实提供，使用前重读。
4. 原文件只使用本会话已由员工审阅发送的片段；未发送草稿/别会话资料不自动混入。

**状态转移**：会话继续→新snapshot追加；新授权/换店不继承不可见旧内容；上下文不足→needs_input。

**异常路径**：摘要服务失败保留原事实并减少旧无关历史；超预算明确停止，不丢当前输入/未处理批量行。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_3.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.3
```

**验收条件**：

- [ ] 长对话仍保留真实候选、原单ID、单位和未完成约束。
- [ ] 过时摘要不能覆盖最新原事实；跨店/撤权快照不可外发。
- [ ] 纯推理和浏览器未发送草稿无持久副本。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-4"></a>

## M4.4 抽取既有 provider 与资源统计

**状态**：implemented

**验证状态**：deferred_to_deepseek；共享provider和真实资源统计已编码及源码审阅，原验收保留。

**全局顺序前置**：M4.3 done。

**执行记录**：编码日期=2026-09-28；新增assistant_runtime_provider.py，原service provider_request/model_reply和stream model_reply_stream保持签名薄包装；SafeDeltas/provider_error迁移并保留旧导出。固定官方DeepSeek/MiMo端点、请求body、模型默认、thinking/temperature、原timeout与接收边界不变，不新增生成token上限或SDK。非流只对首次5xx/Timeout/Transport重试一次，流不重试；原ModelOutputTruncated类型及中文错误保留。非流None finish沿用原兼容合同，显式finish与工具矛盾拒绝；流必须合法finish和DONE。两路完整工具统一验证200边界、唯一非空ID、函数名、完整有限JSON对象/重复键/UTF8，畸形片段不返回执行器。call_model返回ProviderReply(message仅内存且repr隐藏,usage)，legacy只返回原message dict；白名单token计数只接受非负int，缺失及任一未报告请求保持unknown/partial，不把重试末次用量当总消耗。请求数/实际重试数/耗时/合法工具数/background均为安全标量；失败附同一runtime_usage，不附原文/凭据/推理。SSE空choices用量尾包可采集但不能替代结束校验；等待重试被取消不会虚报第二请求。作者/root及两独立代理源码审阅无剩余明确阻断；AST/UTF-8检查退出0，SafeDeltas/provider_error/streaming_response与原HEAD AST一致，三个旧入口签名已核，未执行功能测试。SHA256：provider=4840f7da1bf34d7723fb9fc955add4bc91a526e2a52376e9470913db6a63838d；service=66e5e23541e24f54912bff2a89a9051f496f55575ab22f13e6ed11eaf0cb0df0；stream=56f86ade76c8637c70c8b21fcbc0c8130539eb56eca0abba1c36e22be6e7a7c9。测试=deferred_to_deepseek；原provider fixtures/动态monkeypatch、逐帧SSE、截断与畸形参数、全部边界、缺失usage、重试/取消/错误合同均待集中验证。未导入app、访问DB、联网或改默认开关，无编码阻塞。


**目标**：让新旧执行器使用同一provider协议及截断保护，统计真实usage。

**依赖**：M4.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：service:provider_request/model_reply；business_assistant_stream.py:model_reply_stream/SafeDeltas；现有AssistantConfig。

**允许修改**：新增 app/assistant_runtime_provider.py；旧service/stream仅包装调用抽取实现。外部测试和本项实施记录为共同允许项。

**禁止修改**：不换DeepSeek/MiMo、不安装新Agent SDK、不改模型默认或冻结对照提示词、不在本项付费联网。

**实施步骤**：

1. 逐函数迁移原请求/非流/流处理，旧入口保留同签名；reasoning仅单次工具链内存使用。
2. 严格检测重复tool id、JSON不完整、finish_reason截断及原200索引边界，异常不交执行器。
3. 保留现有timeout/轮次/字符/工具保护，usage缺失记unknown；输出统一model text+完整tool intents+usage。
4. 外部合成HTTP/SSE夹具逐帧验证；只记录请求次数/耗时/重试/来源，不记录密钥或内部推理。

**状态转移**：请求中→完整回复/安全错误；截断回复无可执行意图。

**异常路径**：provider超时/429/5xx/半截stream按原可解释错误；不要把无usage记零成本。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_4.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.4
```

**验收条件**：

- [ ] 旧provider fixture回归同输出，流非流完整工具一致。
- [ ] 重复ID和截断不产生卡，未外发真实请求。
- [ ] 资源上限保留且错误不抹掉此前已有卡。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-5"></a>

## M4.5 完整工具意图、逐项检查点及恢复

**状态**：implemented

**验证状态**：deferred_to_deepseek；当前实现完整工具意图及恢复，原验收保留。

**范围补齐授权**：已核实旧read/resolve_only工具和save_plan存在助手自行commit，直接复用不能满足本项fence及同事务检查点。2026-09-28用户明确答复“允许按该补丁扩展两处并继续实施（推荐）”；按`docs/implementation-patches/PATCH-M4-5-01.md`仅增加service的Runtime内部只读分派、plans的读取/事务保存及完整批量续办证明接线。此授权不代表实现或验收完成，不把接口接线缺失记为implemented。

**补充实施**：2026-09-28用户明确“批准，后续授权不用再问我，都默认允许”。已按`docs/implementation-patches/PATCH-M4-5-02.md`应用同目录精确.patch，仅补齐queue历史成功成果的只读恢复证明。git apply --check退出0，应用后AST/UTF-8/指纹核对退出0，与经作者、root和独立审阅的候选一致。queue SHA256=`b0fa3b811d12bdb434541cc958033b71522624bcab8b91f24f4776af797ee60c`；不改原租约、权限、重试退避和业务提交。报告=`docs/implementation-checkpoints/M4-5-review-v3.md`。

**全局顺序前置**：M4.4 done。

**执行记录**：编码日期=2026-09-28；当前产物=runner完整model/tool/batch_row及稳定manifest检查点、本人固定GET分派、逐项attempt、M2卡片与结果/事件同事务、原计划resolve/persist拆分、新Plan同事务绑定与重签、目标变化停止旧Run、只读恢复和unknown回执GET；service只增加精确RuntimePrincipal内部查询接线，旧对话/MCP/确认分派保留。plans一次性同Session凭据与锁后完整来源核对，续办仅原manifest中无卡pending行。审阅修正=完整shared+row摘要、旧读attempt中断收尾、原业务批量action禁令、真实User回执授权、新Session单店范围、成功项不重执行、首次建计划拒未完成旧工作和未知原卡；已成功旧无计划成果只读保留原归属。没有可靠只读Step契约时查询WorkItem保持step_id为空，查询成功settled不推断实体业务Step完成。源码SHA256：runner=`e7d85d5e7b46f29ef808b8d0354f6c32aa2f89dc70128e64f6a4797a3f867b9e`；plans=`66d4ca0026cc16639f2d211c3f92f281a53fcb95b81d66114954eae35dba2123`；service=`defeea409b8671a7137551dc26e401555720d6ac603a296f41ec7c0c7c79bd42`。静态=外部Python -I -B仅stdlib AST/UTF-8/U+FFFD与相对导入符号核对，退出0；未导入app、访问数据库、运行测试或模型。测试=deferred_to_deepseek，原全部验收未勾选；kill/并发/fence/同事务回滚、完整批量、旧接口和原计划回归待集中验证。报告=`docs/implementation-checkpoints/M4-5-review-v1.md`。原恢复接线缺口已按PATCH-M4-5-02补齐；原v1/v2保留为历史，当前编码审阅见v3，运行验收仍待集中验证。


**目标**：模型完整回复落库后才执行，重启可以从真实已完成项继续。

**依赖**：M4.4 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：registry/runner/queue/events/context/provider；M2.5稳定WorkItem；ARCH E5。

**允许修改**：app/assistant_runtime_runner.py 的execute_tools/checkpoint/recover_items；按用户已授权PATCH-M4-5-01，增加app/business_assistant_service.py的Runtime内部只读分派薄接线，以及app/assistant_runtime_plans.py的原计划读取/无提交保存接口和受限完整批量续办证明。按已授权PATCH-M4-5-02补充queue._safe_retry及两个私有只读证明helper；普通旧调用及原业务规则保持。外部测试和本项实施记录为共同允许项。

**禁止修改**：不处理确认POST、不持久半截调用/推理，不把重试的工具随机分配新行ID。

**实施步骤**：

1. 一次事务保存完整已验证tool/batch_row RunItem及原始稳定行映射；不完整JSON整个片段拒绝。
2. 逐项置running并重新验权；read通过principal native_reader；prepare通过M2.5并检查fence。
3. 完成结果只存必要ref及状态，原授权GET重读详细事实；每行保留独立结果。
4. 恢复纯读可新增attempt，准备先查WorkItem关联；已成功项不再执行，unknown确认交receipt coordinator。

**状态转移**：RunItem pending→running→succeeded/failed/uncertain，取消前未执行项skipped；read WorkItem成功直接settled。

**异常路径**：commit前后kill、半批量、重复intent、旧worker晚回、授权中途变化均有明确检查点。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_5.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.5
```

**验收条件**：

- [ ] 每个崩溃点恢复最多一张同意图卡；完整批量行无丢失。
- [ ] 纯读不造卡；取消保留已准备成果。
- [ ] 恢复不加载持久reasoning或盲重放原业务。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-6"></a>

## M4.6 单次 Run 模型循环与用户输入优先

**状态**：implemented

**全局顺序前置**：M4.5 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：编码日期=2026-09-28；产物=runner.run_once及service内部薄封装，完整意图恢复/新上下文模型链、真实卡计数、原唯一回复和终态/展示同事务；provider每真实外发含内部重试前复验；queue固定Run.usage预算与逐完整工具后台礼让、故障退避不因礼让消耗，retry实际failed才追加最终回复。独立同库短Session复用20秒heartbeat，90秒lease不变；单连接池明确拒绝，不重定向匿名内存库。原24默认/40硬轮数及600秒上限、200待确认容量保持，预算触顶failed，剩余完整行保留；Run成功不代表业务完成。作者/root/独立源码审阅已闭合所报问题；新增HTTP/worker接线留原后项，四flag默认关闭。SHA256：runner=`a04ec5464b0f1eba409b73b98e30e2490d3a8a57a100ec835c9855170e50d17b`，queue=`aa35259c0bd15f50aff5e6472059c8646acb7fa03711a393517f1f3e0ec407eb`；其余受检文件指纹见`docs/implementation-checkpoints/CP-09-v1.md`。静态=stdlib AST/UTF-8/无U+FFFD及新增符号核对，退出0；未导入app、访问DB、运行测试或模型。validation=deferred_to_deepseek，原全部验收未勾选；跨重启预算/最后一轮/超时/心跳/每工具让出/权限变化/唯一终态/重试耗尽/旧入口回归待集中验证。


**目标**：组合上下文、provider、工具检查点，产出可恢复的单轮执行。

**依赖**：M4.5 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：service:conversation/_conversation/interrupted_turn；已实现M4模块；business_assistant_prompt.py。

**允许修改**：app/assistant_runtime_runner.py run_once及必要完整工具边界接线；service增加兼容封装但不开启HTTP新路由；prompt仅runtime事实/工具说明。按用户持续授权登记`docs/implementation-patches/PATCH-M4-6-01.md`，补充provider每次实际外发前守卫、queue固定预算接口与安全工具边界后台让出；不修改模型端点、业务规则、原lease/fence/故障退避及确认。外部测试统一后移，本项实施记录可维护。

**禁止修改**：不删除旧执行路径，不用模型判断授权，不把Run succeeded标成业务目标completed。

**实施步骤**：

1. run_once领取后重验principal/goal_version，组context，调用provider，完整tools交M4.5，按原轮次预算循环。
2. 每次模型外发前复核授权；用户新输入提高排队优先级，后台在完整工具边界让出。
3. 最终AssistantMessage仍按原request_id唯一保存；Run terminal与event事务一致，预算触顶保留已准备卡及剩余原因。 用户回复键<request_id>:reply，后台回复键run:<run_id>:reply，保持原唯一约束。
4. 结构变化取消旧Run并暂停Grant；普通补充资料新Run沿用同plan，不改已冻结提交。

**状态转移**：queued→running→succeeded表示本Run结束；等员工确认时plan仍active/Step awaiting_confirmation；预算/错误failed。

**异常路径**：模型声称已付款但无事实只展示未核实文字且不能更新业务状态；缺模型配置明确503。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_6.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.6
```

**验收条件**：

- [ ] 同request_id最终消息唯一；重复enqueue不多模型调用。
- [ ] 24轮/600秒等硬边界生效，已有卡保留。
- [ ] 只读用户请求无prepare，聊天确认不执行业务。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-7"></a>

## M4.7 事务发件箱及确定来源信号

**状态**：implemented

**全局顺序前置**：M4.6 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28编码及交叉源码审阅完成。最小原事务hooks、可信权限来源helper、Grant仅GET探测、signal批量resolve/persist及逐事件pending CAS已落盘；所有入队与dispatched同事务，失败保留原事件退避。修复任务条件到Case、合法carry_forward旧卡及投影reader单店scope三个接线缺口。全部文件/指纹/作者及独立审阅结论见`docs/implementation-checkpoints/M4-7-review-v1.md`；AST/UTF-8/无U+FFFD静态检查退出0；原事务回滚、并发/失权/乱序/重复及旧入口测试均deferred_to_deepseek，原验收未勾选。当前仅候选信号分发，M4.8接入条件指纹后才具备完整跟进调度；未启动worker/模型/数据库，下一项M4.8。


**目标**：原事实提交与待唤醒信号同生共灭，分发失败可重复处理。

**依赖**：M4.6 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/flow_engine.py；app/flow_api.py任务分派；app/user_access_service.py；service确认结果；plans Grant变化；ARCH E3。

**允许修改**：扩展M3.5已建 app/assistant_runtime_outbox.py 的dispatcher；上述源文件仅同事务emit_wake_event hook；实际权限变更由main持事务的已定位分支hook。真实生产者/事务owner先登记于`docs/implementation-checkpoints/M4-7-source-map-v1.md`。按用户持续授权补充`docs/implementation-patches/PATCH-M4-7-01.md`：queue固定signal入队读取/无commit批量持久接口，principal仅Grant分发前GET身份，以及专用assistant_runtime_access_signals.py可信权限来源信号；不改原业务/权限/提交规则。外部测试后移，本项记录可维护。

**禁止修改**：不增加领域commit、不在业务事务里调用模型/网络、不通过最大event_id推进游标、不存私聊摘要。

**实施步骤**：

1. 复用M3.5 emit_wake_event(db,signal_key,topic,refs)，只add/flush不commit；source key来自真实FlowEvent/任务版本/权限版本/Proposal结果，不再重建另一helper。
2. 先逐个记录hook调用位置与原事务owner，再接flow动作成功、任务分派、卡结果、Grant、权限变更。
3. dispatcher按每条pending CAS处理，重读授权并按对象/任务/计划引用匹配；入队与dispatched同事务。
4. 重复signal命中唯一键视已存在；后到小ID事件仍处理；通知/Run分派失败退避保留pending。

**状态转移**：WakeEvent pending→dispatched；原业务rollback时signal无记录；重复分发同trigger_key只一Run。

**异常路径**：通知失败不改变原业务已成功；乱序/重复/跨店signal不误唤醒别人员私有plan。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_7.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.7
```

**验收条件**：

- [ ] 每个hook有原事务回滚测试；原业务回归不变。
- [ ] 处理一条失败不越过并丢失它，恢复无重复卡。
- [ ] WorkItem/Run按稳定引用连接，未用自由文本匹配。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-8"></a>

## M4.8 持续跟进轮询与无变化零调用

**状态**：implemented

**全局顺序前置**：M4.7 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28编码与交叉源码审阅完成。独立FollowupCheck复用完整条件纯读流程，保持原Run/fence边界；批量来源先全核后写，Step/next_check/必要事实完成及撤Grant与queue入队同事务。signal和tick共用plan+goal+facts指纹，终态不重开，等待/缺资料/原卡异常不反复制卡；原Grant只读补漏5分钟，真实due优先，到期穿过读取窗口立即补查，瞬时失败30秒退避。runner固定收尾原因帮助预算/缺资料等待本人处理。全部文件指纹和具体待测边界见`docs/implementation-checkpoints/M4-8-review-v1.md`；AST/UTF-8/无U+FFFD及实际接口静态核对退出0。无tests/appimport/DB/模型/worker，validation=deferred_to_deepseek；原20次无变化/并发/暂停撤权/完整batch等验收未勾选，下一项M4.9。


**目标**：开启跟进的事项能等前序事实变化后准备下一步，默认不开启。

**依赖**：M4.7 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：queue/outbox/conditions/plans/runner；有效Grant；ARCH E2/E3。

**允许修改**：app/assistant_runtime_outbox.py 调度待到期plan；queue后台入队条件；plans last_evidence/next_check_at更新。按持续授权补充`docs/implementation-patches/PATCH-M4-8-01.md`固定核查凭据/批量持久合同及runner最终事务机器可读收尾摘要；原Run/fence与人工确认门槛不放宽，不增加schema。外部测试后移，本项实施记录允许维护。

**禁止修改**：不对所有旧会话轮询，不创建自动Grant，不以每天定时无条件调用模型，不执行后台confirm。

**实施步骤**：

1. 每5秒分发event，每5分钟只读补漏有效active Grant计划；due_at按next_check_at到时核查。
2. 每轮先验授权→重读依赖事实→比较稳定fingerprint；无变化或前置不满足只更新核查结果，不调用模型。
3. 存在新可办项才以plan+goal_version+来源/事实指纹触发一次后台Run；同指纹终态失败不无限唤醒。
4. 预算失败/缺信息/人工卡等待分别提示处理，不不断重试；暂停/结束/撤权在领取与写回两端生效。

**状态转移**：waiting→条件确证→queued Run→awaiting_confirmation；仍等待不产生新Run；全部必要条件完成→Plan completed并撤Grant。

**异常路径**：休眠恢复到期一次补查；权限失效停止；卡过期不自动反复制卡；无真实前单ID保持waiting。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_8.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.8
```

**验收条件**：

- [ ] 连续20次无变化tick模型调用0；真实变化最多一次准备。
- [ ] 退出有效Grant继续，未开启/暂停/撤销均不准备。
- [ ] 重复event与定时补漏同时命中也只有一WorkItem/卡。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m4-9"></a>

## M4.9 未知确认结果协调与依赖解锁

**状态**：implemented

**全局顺序前置**：M4.8 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28编码与交叉源码审阅完成。原只读receipt resolver保持无状态副作用，独立协调以冻结提交、真实原回执及当前原单权限证明成功；短事务修原Proposal/confirmation/WorkItem并发真实信号，原snapshot/digest/HTTP响应保留。outbox先协调后签发全部条件凭据，runner协调当前Plan前轮卡与完整本Run来源后重读；非2xx条件重查原receipt，不伪造200。最终文件、指纹及新增待测边界见`docs/implementation-checkpoints/M4-9-review-v1.md`。AST/UTF-8/无U+FFFD退出0，无测试/appimport/DB/模型；validation=deferred_to_deepseek。CP-10仅编码放行，原验收全部保留。


**目标**：业务已提交但助手丢失响应时，以可靠原回执修复助手认知。

**依赖**：M4.8 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：receipts；service确认状态；plans/conditions/events/outbox；ARCH E5。

**允许修改**：app/assistant_runtime_receipts.py reconcile_confirmation；runner恢复入口；service仅统一核对结果映射。按用户持续授权补充`docs/implementation-patches/PATCH-M4-9-01.md`：outbox在所有本轮条件凭据之前调用固定当前Plan恢复服务，确保未知卡不因尚无Run而永远无法协调。禁止扩大业务提交能力；外部测试后移，本项实施记录允许维护。

**禁止修改**：不重发POST，不把not_found变failed可重试，不改原业务原单/流水，不让只读GET核对入口偷偷写状态。

**实施步骤**：

1. 恢复先查executing/uncertain的冻结RunItem，再由对应adapter核验actor/store/digest及原结果可见性。
2. confirmed_success在Runtime事务追加证据，更新原Proposal确定结果及WorkItem/Step，发送同事务signal；保留原冻结快照。
3. not_found/unsupported/mismatch保持uncertain并通知本人核对；inaccessible不再暴露旧payload且停止依赖。
4. 员工界面GET仅展示核对结果；后台协调器可落Runtime恢复记录，二者复用只读resolver但副作用边界分离。

**状态转移**：uncertain→可靠核对后completed/settled；其他结果保持uncertain；旧无快照保持人工核对。

**异常路径**：原命令回执不完整、迟到、来源错误、旧版本缺快照均不猜成功；通知失败可恢复而不重复业务。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m4_9.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M4.9
```

**验收条件**：

- [ ] 原业务已成功/助手commit失败可恢复且原API仅调用一次。
- [ ] not_found经过任意轮询都不自动POST。
- [ ] 依赖只在真实证据记录成功后解锁。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-1"></a>

## M5.1 Run、Plan及原卡回执 HTTP 接口

**状态**：implemented

**全局顺序前置**：M4.9 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28编码与交叉审阅完成。五条真实路由接Run/Plan/只读回执及版本取消，冻结原HTTP身份并在异步GET前后/回包前复验；Run幂等优先于模型配置，GET关闭开关仍可读，原session仅补实际run_id。完整关联引用按原GET过滤，v1计划只读兼容、无自动升级或跟进授权。文件、静态指纹及待测边界见`docs/implementation-checkpoints/M5-1-review-v1.md`。AST/UTF-8/无U+FFFD退出0；无tests/appimport/DB，validation=deferred_to_deepseek。继续M5.2。


**目标**：为新前端提供明确202入队、读取、版本取消和只读核对合同。

**依赖**：M4.9 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：business_assistant_api.py；schemas/queue/principal/plans/receipts；app/main.py router注册。

**允许修改**：新增 app/assistant_runtime_api.py；app/main.py仅include_router；原session_view附加last_request.run_id。外部测试和本项实施记录为共同允许项。

**禁止修改**：不新建confirm路由、不返回submission_snapshot/登录hash、不信任请求中的身份，不变更原确认返回形状。

**实施步骤**：

1. 逐项实现ARCH F中POST runs、GET run、POST cancel、GET plan及GET execution-result。
2. 保留CSRF、single_store、owned_session；所有对象先权限过滤再返回；跨人/跨店404，expected_version冲突409。
3. runtime关闭POST runs503；get已有授权记录可读，旧确认接口可用。
4. 重复request_id内容相同返回同RunView，不同内容409；原session last_request仅补充run_id兼容字段。

**状态转移**：POST accepted→202 queued；GET无业务变更；cancel按Run合法转换。

**异常路径**：队列不可用/配置缺失503；未知结果查询只返回ReceiptLookup，不清卡/重试/改业务。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_1.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.1
```

**验收条件**：

- [ ] 真实ASGI Cookie/CSRF方向测试通过，非法身份参数422。
- [ ] JSON字段逐项匹配ARCH，无敏感快照泄露。
- [ ] GET核对不改变Proposal/业务数据，原API回归通过。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-2"></a>

## M5.2 SSE 事件订阅及旧消息接口兼容

**状态**：implemented

**全局顺序前置**：M5.1 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28编码及交叉审阅完成。新增共用accept/open事件订阅，逐帧fresh授权、连续seq、多批终态排空和无写心跳；旧消息开关分派、600秒有界等待、精确原请求最终回复及delta兼容均落盘。断线只关闭订阅，原legacy流AST未变；session状态取真实Run。最终文件、指纹及具体待测点见`docs/implementation-checkpoints/M5-2-review-v1.md`。AST/UTF-8/无U+FFFD退出0，无测试/appimport/DB；validation=deferred_to_deepseek，继续M5.3。


**目标**：新旧消息入口共用同一Run，页面关掉后授权允许的后台工作可继续。

**依赖**：M5.1 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：business_assistant_api.py message路由；business_assistant_stream.py:streaming_response；events/queue/runner；ARCH F。

**允许修改**：assistant_runtime_api.py SSE；business_assistant_stream.py订阅包装；business_assistant_api.py消息开关分派。按持续授权补充`docs/implementation-patches/PATCH-M5-2-01.md`的service.session_view真实Run状态投影。外部测试后移，本项实施记录允许维护。

**禁止修改**：不删除原legacy执行器，不将网络断开当业务取消，不改变旧接口成功SessionView形状。

**实施步骤**：

1. 实现after_seq补读+实时tail，SSE id=seq；每批发送前重新鉴权，不继续吐失权缓存。
2. runtime开时旧messages入同一Run等待，旧stream把持久事件映射原格式；runtime关时保持原路径。
3. 连接断开仅终止订阅；手动停止调用cancel；旧等待超时返回503/504和原run_id。
4. 重发同request_id恢复原Run，多个订阅者不启动多次模型；心跳只保连接。

**状态转移**：SSE connected→disconnected/reconnected独立于Run；logout普通Run停，Grant Run按授权可继续。

**异常路径**：反向代理缓冲、重连重复seq、旧event缺失、客户端迟到、401/403均有明确行为。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_2.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.2
```

**验收条件**：

- [ ] 断流后有效Run不因订阅finally被取消；重连不重复文字/卡。
- [ ] 兼容旧流事件与无流返回；runtime=false旧助手可操作。
- [ ] 撤权后不再发送后续缓存数据。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-3"></a>

## M5.3 授权事项投影与跟进控制 API

**状态**：implemented

**全局顺序前置**：M5.2 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28新增assistant_runtime_workspace.py及API共享PlanView/workspace/followup路由；原mine/open任务与汇总排除、本人Session卡及计划、严格原GET来源过滤、五分计数、稳定游标、异步后来源复验、本人Cookie/CSRF及原Grant状态机均已源码交叉审阅。修正未核实confirm投影、临时查询失败误当空项、待确认文案及关联Plan来源；侧栏卡仅open。AST/UTF-8/无U+FFFD检查退出0，最终两文件SHA-256见docs/implementation-checkpoints/M5-3-review-v1.md；没有运行测试、模型、迁移或服务。原验收及并发/隐私/分页异常均待DeepSeek，CP-11仅编码放行。


**目标**：形成待我处理/跟进中/已结束侧栏及本人显式跟进按钮。

**依赖**：M5.2 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/task_views.py；business_assistant_workboard.py；workspace DTO；plans Grant服务；原task API。

**允许修改**：新增 app/assistant_runtime_workspace.py；assistant_runtime_api.py workspace和followup路由；schemas仅合同既有字段。外部测试和本项实施记录为共同允许项。

**禁止修改**：不改原任务授权query、不先分页再筛权限、不混算任务/卡/计划总数，不让首屏自动创建会话。

**实施步骤**：

1. workspace加载原任务、本人有效卡与计划，按授权过滤后分类计数分页；稳定key及游标。
2. counts五分项保持分开，同task在多个模块仍以真实task_id处理，禁止相加冒充业务总数。
3. followup POST调用M3.5含CSRF/expected_version；allowed_actions从当前授权和状态产生。
4. workspace响应包含四features；模型就绪复用现有GET /status的ready/message，不重复定义model_ready。模型不可用仍返回真实事项和人工route。

**状态转移**：首屏GET只读；开启/暂停/恢复/结束按Plan/Grant转移；读通知不完成原任务。

**异常路径**：空列表不等于资金或库存全完成；失权关联移除并正确调整计数；并发版本冲突要求刷新。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_3.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.3
```

**验收条件**：

- [ ] 角色/门店过滤发生在count/limit前；分页无漏/重。
- [ ] GET调用0模型/0prepare，未自动创建session或Grant。
- [ ] 同事只见原任务授权内容，不见他人私聊/卡。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-4"></a>

## M5.4 站内提醒去重和协作隐私

**状态**：implemented

**全局顺序前置**：M5.3 done。

**验证状态**：deferred_to_deepseek。

**执行记录**：2026-09-28完成workspace通知生成/读取/已读、API与outbox接线；按PATCH-M5-4-01补service/plans/runner/queue/flow真实源信号。仅真实本人当前店源产生固定文案提醒，原卡/Plan分开结束，同Run去重，真实执行阻断投影、三分钟未知核查与通知独立开关均经源码交叉审阅。9文件AST/UTF-8/无U+FFFD检查退出0，SHA-256见docs/implementation-checkpoints/M5-4-review-v1.md；未运行测试、应用、数据库、迁移或模型。Case外原引用的固定可见性在对应M7适配时补齐，当前安全不生成；所有原验收及新增去重/并发/隐私场景移交DeepSeek。


**目标**：把真正需员工处理的卡、补充项、异常与原任务变化通知到正确本人。

**依赖**：M5.3 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：workspace/outbox/models；原Task分派与read权限；ARCH F。

**允许修改**：assistant_runtime_workspace.py 通知生成/读取/已读；outbox分派接线；assistant_runtime_api.py notifications。外部测试和本项实施记录为共同允许项。

**禁止修改**：不发飞书/邮件/短信，不创建共享会话，不替同事确认，不以聊天全文做通知摘要。

**实施步骤**：

1. 来源限定真实proposal/plan/task及状态版本，用source_key+kind唯一；没有可见引用不创建明细提醒。
2. GET本人同门店通知重验引用可见性；POST read幂等且不改原任务；源事项确已结束才resolved。
3. 同事协作沿原task assignee/岗位队列；只交接原单/任务引用，接手者新会话按本人权限读取。
4. 通知失败记录可重试，不改变原API成功；重复事件只一次提醒，优先实际attention事项。

**状态转移**：unread→read→resolved仅真实条件；读通知与业务完成独立。

**异常路径**：转岗、撤店、任务再次转交、来源删除、重复/乱序signal均不泄露旧私聊或错通知。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_4.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.4
```

**验收条件**：

- [ ] 两员工交接能看到各自授权内容，其他员工私聊/卡不可见。
- [ ] 重复源事件单提醒，失败恢复不重复业务。
- [ ] 已读不解除等待、不完成Task、不触发模型。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-5"></a>

## M5.5 MCP 草稿工具兼容及共享互斥

**状态**：implemented（2026-09-28 集中测试阶段完成源码审阅与外部实测，见下）

**全局顺序前置**：M5.4 done。

**验证状态**：部分实测通过；跨进程/并发与准备类工具全链仍待补。

**执行记录**：2026-09-28 完成编码（Astra 批次 a40f7f4）与本轮实测。外部套件 `V/tests/runtime/test_m5_5.py` 7 项 + 受影响原回归 20 项，run `20260928T060804Z-7aa5208e93` passed。实测确认：工具目录保持 business_v1 旧结构且无确认/授权工具；只读工具经真实 HTTP 端点执行只产生 tool 型 RunItem（无 model/confirmation）；同请求号重放不新增行；同请求号不同参数 409；关闭 Runtime 后同请求号 503+accepted+原 run_id 且不重放 legacy 写入。测试还发现并修复 5 处缺陷：`_frame` 意图自比改为与卡片内容绑定、claim 后前置步骤纳入 fence 释放、重放提示不覆盖工具 notice、批量计数自洽、legacy 工具循环整表被拒时回 422 工具结果（恢复 M3.1 预校验打断的原契约）。详见 `docs/implementation-patches/PATCH-M5-5-02.md`、`docs/implementation-checkpoints/M5-5-review-v1.md`。未覆盖：真实并发、跨进程 worker/HTTP 竞争、退避窗口时序、真实 MCP 客户端重试、准备类工具建卡与去重。源码指纹 `fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`。


**目标**：旧外部工具仍以本人身份读/准备，和worker不会交错破坏会话。

**依赖**：M5.4 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：business_assistant_api.py:/tools与/sessions/{id}/tools/call；registry/queue/runner；原工具回归。

**允许修改**：business_assistant_api.py工具调用包装；registry/queue必要共享入口。外部测试和本项实施记录为共同允许项。

**禁止修改**：不扩展MCP为通用服务器、不暴露confirm或Grant开关、不让MCP请求隐式调用模型。

**实施步骤**：

1. 保留旧ToolCall字段及返回形状；registry提供原目录，工具数与reviewed目录一致。
2. 用共享session CAS忙租约与稳定request_id意图键；MCP读取/计划/准备同一检查点路径，但模型调用0。
3. 同请求重复返回已存在成果，不重建卡；业务确认继续原员工点击接口。
4. 释放busy只清理自己持有token，超时保持可查询部分结果及明确未完成说明。

**状态转移**：MCP idle→busy→released；worker/MCP冲突409或按原契约等待，不并发写同session。

**异常路径**：重复call、并发网页请求、超时后worker恢复、工具参数超长均不得遗失原卡或越权。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_5.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.5
```

**验收条件**：

- [ ] 旧MCP兼容suite通过；无确认/授权工具出现。
- [ ] 并发准备唯一WorkItem/卡，模型请求0。
- [ ] 超时后原结果可查，错误释放不会清新worker锁。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-6"></a>

## M5.6 worker CLI、关闭和安全健康信息

**状态**：implemented（2026-09-28 由 Codex 侧实现并完成外部实测）

**全局顺序前置**：M5.5 done。

**执行记录**：2026-09-28 新增 `app/assistant_worker.py`（唯一新增文件，未改 config、未加迁移/开关、未动 app/cli.py）。外部套件 `V/tests/runtime/test_m5_6.py` 13 项 + 受影响原回归 `tests/test_app.py`，run `20260928T061011Z-d295c8ac6c` passed。实测确认：import 不启进程；启动校验拒绝缺 DATABASE_URL、缺 Runtime 表、无迁移历史、只到 h52j 四类实例；心跳键长 58≤60、值只有 at/source/instance/error、清理只碰预留前缀且保留存活同伴；health 分辨 worker 过期与租约过期待恢复、Runtime 关闭报 runtime_disabled、输出无数据库 URL；tick 顺序 reclaim→claim、每周期最多一个执行槽、Runtime 关闭不领取；执行中取消直接上抛不产生第二次领取。实测发现并修复 worker 双启动缺陷（两次连续 start 会创建两个 serve 循环）。详见 `docs/implementation-checkpoints/M5-6-review-v1.md`。未覆盖：两个真实进程同时运行、真实 Ctrl+C/SIGTERM 时序、真实 PostgreSQL、M5.7/M5.8 的启动与恢复。源码指纹 `fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`。


**目标**：提供Windows嵌入和Linux独立进程共用的单槽worker核心。

**依赖**：M5.5 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：assistant_runtime_queue/outbox/runner；app/cli.py；app/models.py:AppMetadata；ARCH H。

**允许修改**：新增 app/assistant_worker.py；config仅既有开关引用。外部测试和本项实施记录为共同允许项。

**禁止修改**：不自动迁移/初始化数据库，不复用日报Scheduler，不import即启动，不在健康输出含用户/客户/DB URL/密钥。

**实施步骤**：

1. 实现Worker.start/stop及async tick；5秒检查、20秒心跳、每次最多1执行槽；--once执行一次周期后退出。
2. CLI启动前校验明确实例配置及迁移头，缺h53报错；只操作现有已准备实例。
3. 用AppMetadata保留本worker 32字符UUID hex（完整key≤60字符）安全心跳：预留assistant_runtime_worker:前缀，仅时间/源码指纹/实例安全标识/错误码；每worker独立，清理本前缀7日前过期记录。
4. --health只读聚合60秒内心跳、队列数及最近完成时间，退出码反映健康；stop停止领取并在安全边界结束，旧lease按CAS恢复。

**状态转移**：stopped→running→stopping→stopped；功能关闭不再领取；进程死亡后expired lease可安全恢复。

**异常路径**：缺配置/缺迁移/数据库不通启动失败；空队列也有心跳；信号中断不能进入原业务POST。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_6.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.6
```

**验收条件**：

- [ ] --once不常驻；import不启进程，Ctrl+C/终止可恢复。
- [ ] 两个进程即使启动也不重复准备；心跳清理只碰预留元数据。
- [ ] health能分辨Web存活但worker过期，无业务明细输出。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-7"></a>

## M5.7 Windows 预览嵌入同实例 worker

**状态**：implemented（2026-09-28 由 Codex 侧实现并完成外部实测）

**全局顺序前置**：M5.6 done。

**执行记录**：2026-09-28 修改 `app/main.py`（新增 `_embedded_runtime_worker`/`_stop_embedded_runtime_worker`，lifespan 内按条件嵌入与停止，模块级单例）。外部套件 `V/tests/runtime/test_m5_7.py` 7 项 + 受影响原回归 `tests/test_local_preview.py` 16 项，run `20260928T062457Z-eb0d2c567c` passed。实现顺序固定为：`HUAKANGOS_LOCAL_PREVIEW` → Runtime 开关 → 预览根目录 → `marker_from_disk` 磁盘标记 → 之后才 import worker → 只读实例校验 → 一个 worker。实测确认：普通 Web 不嵌入；开关关闭不读标记不启动；标记先于 worker 导入（用会失败的替身证明未调用）；缺预览根明确拒绝；真实 lifespan 只启动一个并复用同一对象、关闭时 stop 一次；预览目录只允许 LOCALAPPDATA/huakangos 之下；Web 与 worker 的库标识/源码指纹一致且 health healthy。未改动 local_preview/preview_runtime/预览脚本（原实例守卫与源码身份校验已满足合同）。`tests/test_preview_runtime.py` 的两个子进程节点带 phase-B 专用夹具授权，只能在 M0.2.B 运行，本项不重复选取。详见 `docs/implementation-checkpoints/M5-7-review-v1.md`。未覆盖：真实 Windows 预览实例启动/退出/再启动、强杀后租约恢复。源码指纹 `94da7d7cc30bfd49d978714035bce690a7b93808e34f0a569508cc06254b8c01`。


**目标**：预览Web开启新Runtime时自动使用相同配置的worker，关闭时正确结束。

**依赖**：M5.6 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：app/local_preview.py:configure/main；app/main.py:lifespan；app/preview_runtime.py；scripts/preview_launcher.ps1；start-preview.ps1。

**允许修改**：app/main.py lifespan仅HUAKANGOS_LOCAL_PREVIEW+runtime条件启动/停止worker；app/local_preview.py必要接线；预览脚本仅同实例参数传递。外部测试和本项实施记录为共同允许项。

**禁止修改**：不重置原预览账号/数据、不改日报关闭值，不新开可见helper窗口，不从另一目录.env加载配置。

**实施步骤**：

1. 必须configure(root)和marker_from_disk验证之后才import app/worker；沿原source identity校验。
2. lifespan仅已标记local preview且runtime=true嵌入一个Worker；普通Web部署不嵌入。
3. 原launcher实例守卫防重复，新的worker不再独立prepare数据库；停止复用Worker.stop。
4. 仅在外部合成实例验证启动/退出/再次启动；目前用户原预览不访问。

**状态转移**：预览启动→Web+同库worker；关闭→停止领取；再启动→按持久Run/Grant恢复。

**异常路径**：重复launcher、路径标记不符、迁移缺失、config导入顺序错误明确拒绝；关闭电脑期间不承诺运行。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_7.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.7
```

**验收条件**：

- [ ] 合成Web/worker数据库安全标识与源码指纹一致。
- [ ] 日报仍off，原预览账号不变更。
- [ ] runtime=false仅原Web可用，启动两次不产生两个嵌入worker。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

<a id="m5-8"></a>

## M5.8 Linux worker 部署定义和开关回退

**状态**：implemented（2026-09-28 由 Codex 侧实现并完成外部静态实测）

**全局顺序前置**：M5.7 done。

**执行记录**：2026-09-28 修改 `compose.yml` 新增显式 profile 的 `assistant-worker` 服务（同镜像/同 .env/同数据卷、`command: python -m app.assistant_worker`、`--health` 健康检查、`stop_grace_period: 90s`、不暴露端口），新增 `docs/assistant-runtime-operations.md`；未改 `Dockerfile` 与 `start.sh`，无产品代码改动。外部套件 `V/tests/runtime/test_m5_8.py` 7 项 + 受影响原回归 17 项，run `20260928T063142Z-43abd9857f` passed（未构建或启动任何容器）。实测确认：worker 显式 profile 才启动、命令不含 cli/init/migrate/start.sh/uvicorn、Scheduler 显式关闭、无 redis、Web 与 worker 的镜像/库/挂载/安全限制逐项一致、健康检查用 `--health`、运维文档覆盖四开关与备份/回退边界且无密钥样例。详见 `docs/implementation-checkpoints/M5-8-review-v1.md`。未覆盖（属 M8.8）：真实 Linux 构建/启停/healthcheck 轮询与恢复演练、真实 PostgreSQL、两实例并发。源码指纹 `9360f51e72d2d7c864473fb50d2ae65fd9f63a9805a2dce889be2adce3d9f9c2`。


**目标**：交付使用同镜像、同明确数据库配置的独立worker定义。

**依赖**：M5.7 done；同时读取ARCHITECTURE中本项合同。全局顺序不得跳过。

**涉及文件（必读）**：Dockerfile；compose.yml；start.sh；app/assistant_worker.py；README.md；ARCH H。

**允许修改**：compose.yml新增独立assistant-worker服务及显式profile；新增 docs/assistant-runtime-operations.md；Dockerfile仅复用当前镜像所需细调。外部测试和本项实施记录为共同允许项。

**禁止修改**：不部署公司服务器，不运行compose up生产服务，不将Web入口脚本的迁移/初始化并发跑两遍，不新增Redis。

**实施步骤**：

1. worker command明确python -m app.assistant_worker，复用同镜像/env/数据挂载和安全限制，默认profile不自行启用。
2. web仅原Web+日报行为；助手worker不执行start.sh中的初始化，先独立升级经授权副本再启worker。
3. healthcheck用--health；restart及优雅停止时间覆盖安全退出；日志只错误类型与运行ID。
4. 运维文档写清四开关、worker健康、备份先行、同库同版本、停止/恢复及不降级删表；真实Linux验证M8.8。

**状态转移**：部署定义待运行；关闭功能→停止新任务并保留已有原单与Runtime记录；重新开启按当前授权恢复。

**异常路径**：错库/错版本/无h53/环境缺失必须失败，不兜底SQLite；这里只验证静态定义，不称生产已部署。

**验证命令**：M0建立后使用统一runner，登记外部 `$V/tests/runtime/test_m5_8.py` 及本项涉及的原回归；不在源码根裸跑pytest。

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M5.8
```

**验收条件**：

- [ ] compose配置解析与命令参数校验通过，未启动真实部署。
- [ ] Web/worker挂载和明确DB来源一致，单独worker不会初始化账号。
- [ ] 运维步骤无密钥样例和破坏性降级；实际Linux留明确未验收项。
- [ ] 本项定向测试及manifest列出的受影响原回归通过，记录本次源码指纹、命令、退出码和证据路径。
- [ ] diff只涉及允许范围；未触碰公司库/原预览库、未擅自调用真实模型；状态更新有实际证据。

## M6：助手工作台、全系统入口、跟进控制与站内通知

本章是 `total_plan.md` 的实施细化，产品和接口以根目录 `PROJECT_SPEC.md`、`ARCHITECTURE.md` 为权威；本章不新增另一套协议。一次只实施一个 M6.x；完成该项后先更新状态及证据，再检查顶部CP门禁。普通turn只完成一项；目标模式仅在已获准批次内串行，到CP-14/15/16必须停止，不自动跨检查点、不并行实施后项、不跨过未完成依赖。技术栈固定为现有原生JavaScript、CSS、FastAPI页面；不引入React、npm工程、前端状态库或新权限体系。里程碑实施状态只用todo/in_progress/done/blocked；测试运行结果单独记录，不能把测试passed直接当里程碑done。

## M6 共用约定与依赖

### 已确定的实现位置

- `web/assistantruntime.js`：运行 REST/SSE、事件序号、请求去重、订阅连接和内存状态；不生成业务动作、不确认业务。
- `web/assistantworkspace.js`：事项侧栏、页面局部更新、统一交接守卫、跟进与通知展示。
- `web/assistantworkspace.css`：仅作用于新助手工作台的布局及窄屏样式，选择器统一以 `.ba-runtime-workspace` 为根；不批量重写原页面 CSS。
- `web/businessassistant.js`：保留原卡片呈现、问题补填、文件/问题入口及原确认调用，只接入上述两个模块。
- `web/businessassistantwork.js`：保留旧计划读取，增加 v2 PlanView 展示适配；不在前端推进步骤。
- `web/app.js`：默认路由、侧栏顺序、清理上下文和原待办入口接线。
- `web/index.html`：在现有 `businessassistantfiles.js` 之后、`workflowactions.js` 之前按顺序加载 `assistantruntime.js`、`assistantworkspace.js`；新 CSS 放在 `simpleui.css` 之后。所有脚本仍使用 `defer`。

主导航只有现有一列，助手内部只有“事项侧栏＋当前事项”两列；确认卡在当前事项内，不形成第三列常驻卡片栏。原十模块、原单操作、文件上传、附件授权及人工待办全部保留。

### 外部依赖 ID

| ID | 本章消费的已完成合同 |
| --- | --- |
| M0 | 当前源码安全镜像、隔离合成库、统一外部验证 runner、基线恢复与指纹 |
| M5.1 | 新 Run REST、稳定 request_id、状态读取和显式取消 |
| M5.2 | 持久 Run 事件、SSE 补读、旧消息/流式消息兼容包装 |
| M5.3 | workspace 查询、PlanView、Grant 控制与服务器状态/权限投影 |
| M5.4 | 私有通知查询、已读更新、去重及读取时重新授权 |
| M5.5 | 原 MCP 工具兼容，未增加确认或 Grant 工具 |
| M5.6 | 共用 worker CLI、单槽执行、安全退出及健康读取 |
| M5.7 | Windows 预览同实例嵌入 worker，不接触原预览 |
| M5.8 | Linux 独立 worker 定义及四开关回退合同；本项不代表实际部署 |
| M2.2、M2.4、M2.6、M4.9 | 真实 refusal 分类、冻结确认、只读回执与未知结果恢复 |

总计划原 P8/P9 不能理解为先实现所有 UI 再做通知后端。全局顺序以主实施索引为准，M5.8完成后进入M6；数据依赖包括M5.3先于M6.3/M6.6、M5.4先于M6.7。M6 禁止临时用 mock 后端、浏览器 localStorage 或旧静态目录冒充正式 workspace/notification 数据。确定性UI测试可注入合成模型回复，但浏览器必须连接当前源码镜像中的真实HTTP与M5.6 worker；M5.7/5.8的启动定义不授权启动原预览或公司部署。

### 消费根架构的接口合同

下列字段摘录根目录 `ARCHITECTURE.md` 的F节及“补充wire合同”，当前已冻结。M1.1实现共同schema，M5实现接口，M6只消费；前端不能自行改名或扩充后端字段。ID保留其原类型：session/plan/run/proposal为字符串，原Task ID为整数，对象ID服从受评审`BusinessObjectRef`。可空/可省略字段按共同schema处理，不以假ID代替。实现与根合同不符时修复所属前置项，不在JS中另定义一套线上协议。

1. `GET /workspace` 返回：

```text
WorkspaceView = {
  features: {home, runtime, followup, notifications},
  counts: {
    native_tasks, pending_proposals, attention, following, finished
  },
  groups: [{key: "attention"|"following"|"finished", items, next_cursor}],
  checked_at
}
WorkspaceItem = {
  key,
  kind: "native_task"|"proposal"|"plan",
  session_id?, plan_id?, task_id?, proposal_id?, object_ref?,
  title, status, status_label, waiting_reason?, due_at?, manual_route?,
  allowed_actions[], updated_at
}
```

默认limit30、上限100；服务器先权限过滤，再计数/分页、排序及仅按相同`task_id`合并。单组继续读取使用`GET /workspace?group=<key>&cursor=<opaque>&limit=30`；前端按M5.3的共同响应DTO处理，不解析cursor、不自行重新归组。`counts`字段分别展示，禁止相加为“业务总数”，也不擅自按中文解释重算计数。模型就绪仍读现有`GET /status`的`ready/message`，不要求workspace重复添加model_ready/model_message。汇总门店按M5.3授权只读投影；不能浏览或接管其他员工私聊。

2. `POST /sessions/{id}/runs`请求固定为`{request_id,content,thinking,plan_id?,entry_context?}`，无关联值就省略，不发送员工/门店/角色权限，也不额外发送expected_version。返回HTTP202的`RunView`；运行ID使用`response.id`。同request_id同内容返回同一RunView.id，不同内容409；UI不要求reused字段。

```text
entry_context = {
  source_type: "task"|"object"|"workflow",
  intent: "query_status"|"explain_prerequisites"|"prepare_action",
  task_id?, object_ref?, workflow_id?
}
```

entry_context按source_type恰好携带对应一种引用，服务器重新解析并验权/验证发布目录。模块和快捷操作使用真实发布workflow_id，不增加任意module/URL/action参数。`contextEpoch`只在浏览器守卫中使用，不是服务端身份字段。

3. `GET /runs/{id}` 返回：

```text
RunView = {
  id, session_id, plan_id, version,
  status: "queued"|"running"|"succeeded"|"failed"|"cancelled",
  last_seq,
  display: {phase, text, revision},
  result_refs[], error?, allowed_actions[]
}
```

`display`是已脱敏业务进度，禁止包含原始推理、凭据、工具参数或模型生成的完成事实。取消能力由`allowed_actions`中的`cancel`控制；`POST /runs/{id}/cancel`必须提交`{expected_version: RunView.version}`。刷新恢复读取根合同已有`SessionView.last_request.run_id:string|null`，有值才GET该Run；null表示没有可恢复引用，不能按最后一条消息的位置猜Run或新建Run。

4. `GET /runs/{id}/events?after_seq=N`按根架构订阅/补读SSE，每条id为seq；data为`RunEventView={run_id,seq,type,payload,created_at}`，不另造kind/data包装或JSON分页接口。类型采用`run.queued/run.started/run.progress/tool.finished/proposal.prepared/plan.updated/run.completed/run.failed/run.cancelled`；run.progress的payload固定`{display:RunView.display}`，其他事件只含已提交对象的安全引用，需要详情时重读对应GET。展示文字从RunView.display的text/revision恢复，最终回复从原AssistantMessage/session读取，禁止拼接不完整工具调用。事件缺口重新从lastAppliedSeq订阅；鉴权失效终止并清理，409先读RunView/session核对，不发新Run。未知type不解释成动作，刷新一次RunView后保留“不支持的进度信息”提示，不引入自定义cursor错误码。

5. `GET /plans/{id}` 返回：

```text
PlanView = {
  id, session_id, version, goal_version, goal, status,
  steps[],
  grant: {status, enabled, stop_reason},
  allowed_actions[]
}
PlanStepView = {
  key, position, title, wait_for, status, wait_reason,
  proposal_id?, proposal_ids[], object_ref?, manual_route?
}
```

Plan/Grant/step状态遵循根架构，不由UI扩充。PlanStep保留原工具title/wait_for作为脱敏说明；缺标题时从已发布工作流/原表单取得或显示“第N步”。title/wait_for均不是完成证据，不能解析为执行条件。跟进请求为`POST /plans/{id}/followup`，body`{action,expected_version}`，action限定`enable/pause/resume/revoke`且必须在allowed_actions内。`enable`首次授权，`pause`暂停，`resume`恢复，`revoke`对应“结束这件事”。展示用固定中文枚举映射，不要求PlanView增加status_label；授权停止原因使用grant.stop_reason。旧版/新版计划均由服务器PlanView投影和allowed_actions表明可办动作，UI不必另索取engine_version。

6. `GET /notifications?cursor=<opaque>&limit=30`返回根合同`NotificationList={items:NotificationView[],next_cursor,unread_count}`，默认limit30、上限100。`NotificationView={id,kind,safe_summary,status,created_at,read_at,session_id?,plan_id?,proposal_id?,task_id?,manual_route?}`。`POST /notifications/{id}/read`幂等标已读并返回更新后NotificationView、不改业务。通知不含另一员工会话/卡片；manual_route只来自当前授权引用。没有自己的有效session_id时，有task_id就走统一任务交接，有manual_route就走原页面；两者都没有则只显示安全摘要，不猜object_ref或链接。

7. `GET .../execution-result`返回根架构`ReceiptLookup={status,checked_at,object_refs[],evidence_refs[],reason_code}`，status为五种固定值。只读、不更新卡片；前端不能索取另造的message/manual_route字段或直接把proposal写成succeeded。中文提示按五种status与已知reason_code固定映射；原单链接从已授权原session/proposal链接或对象读取结果取得，不从回执文字拼路径。

### 验证目录、命令和纪律

```powershell
$RepoRoot = 'C:/Users/tiefu/.codex/worktrees/edb5/HuaKangOS'
$V = 'C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'
$VPython = "$V/.venv/Scripts/python.exe"
```

每次实际执行前核对当前工作树绝对路径；若实施时换了受管工作树，只修改 `$RepoRoot`。外部测试命名固定为 `$V/tests/frontend/test_m6_1.cjs` 至 `test_m6_8.cjs`，HTTP 浏览器测试为 `$V/browser/test_m6_1.py` 至 `test_m6_8.py`。不把测试搬回仓库，不使用 `npm build`。

必跑命令分别在各项列出。runner 按 M0 创建本次当前源码镜像、合成夹具、输出目录并记录源码指纹；不得将旧归档 app/web 作为被测程序。runner 的 M6 适配依次执行对应 Node 原生测试及 Python 浏览器测试，内部调用约定为：

```text
node --test <V>/tests/frontend/test_m6_N.cjs
python -X utf8 <V>/browser/test_m6_N.py
  --source-root <本次安全镜像>
  --sandbox-root <本次合成夹具目录>
  --output <本次输出目录>
```

runner 向 Node 注入 `HUAKANGOS_TEST_SOURCE_ROOT` 和 `HUAKANGOS_TEST_OUTPUT`；测试缺少这些路径时失败，不能回退到开发者机器的默认库。Node 用 `node:test`、`assert`、`vm` 读取镜像中的真实 JS，网络由定向假响应驱动；浏览器用 Playwright Chromium 和真实本地 HTTP，不以 ASGI 桥接或直接调用页面函数冒充交互验收。浏览器脚本先验证沙箱位于 V 内、非原预览/公司路径，在 import app 前设置独立配置；随机 loopback 端口启动应用与需要的 worker。必须通过登录表单取得真实 Cookie、点击真实按钮。合成模型响应仅用于确定性 UI 测试，报告必须写“非真实模型成绩”。

每个测试进程关闭浏览器、HTTP 服务和 worker，退出码非零一律记录失败；截图仅用合成数据。任何副作用测试都统计实际业务接口请求，不能只根据 DOM 文案判定未自动办理。

<a id="m6-1"></a>

## M6.1：只增加 Run REST/SSE 客户端和纯状态归并

**状态**：implemented（2026-09-28 由 Codex 侧实现并完成外部实测）

**全局顺序前置**：M5.8 done（CP-13 已放行后续编码）。

**验证状态**：Node 合同 + 接线/路由形状实测通过；真实浏览器同源与 SSE 连接头属 M8.4。

**执行记录**：2026-09-28 新增 `web/assistantruntime.js`（IIFE，唯一出口 `globalThis.AssistantRuntime`：submitRun/getRun/subscribeRun/cancelRun/disposeContext/snapshot），`web/index.html` 按 M6 约定在 businessassistantfiles.js 之后、workflowactions.js 之前加 defer 标签；未改 `web/businessassistant.js`、确认路径、后端接口或迁移。外部套件 `V/tests/frontend/test_m6_1.cjs` 15 项（经已评审 `tests/m02_node_adapter.py` 事件级证据）+ `V/tests/runtime/test_m6_1.py` 7 项，run `20260928T092523Z-1ef70a74e0` passed。实测确认：重复/乱序/缺口事件的 seq 处理与 after_seq 补读、display 按 revision 替换、1/2/5/15 秒退避、后台暂停与回前台立即重读、终态读回一次 session 后关闭订阅、unsubscribe/dispose 零服务器调用、409/401/403/404 分类、切店迟到事件不应用也不推进序号、真实服务器接受该路由形状。实测发现并修复 3 处客户端缺陷（statusFailure 不抛出、陈旧上下文推进序号、退避不收敛）。详见 `docs/implementation-checkpoints/M6-1-review-v1.md`。源码指纹 `ee2752b6bad230d227b4c95cd6d4fedf42da38e3c466690fabc79442851ee2d1`。


**目标**：建立可重连、可丢弃旧上下文、无业务副作用的浏览器 Runtime 客户端；本项不替换员工现用发送按钮。

**依赖**：M0.1、M0.2、M5.1—M5.8均done，尤其M5.6—M5.8启动/关闭与开关合同；不得跳过全局索引。

**先读**：`web/businessassistant.js`的`businessAssistantRequest()`、`businessAssistantReadEvents()`、`businessAssistantAlive()`、`clearBusinessAssistantSession()`；`web/app.js`的`api()`、`requireStoreContext()`；`app/assistant_runtime_api.py`、`app/assistant_runtime_schemas.py`的实际合同。

**允许写**：新建 `web/assistantruntime.js`，为其增加 `web/index.html` script 标签；外部 `test_m6_1.cjs`、`test_m6_1.py` 及 runner 的 M6.1 条目。禁止修改模型/provider、业务 schema、原确认路径和当前 UI 行为。

**具体改法**：

1. 使用IIFE暴露唯一`globalThis.AssistantRuntime`，本地函数为`submitRun(sessionId,body)`、`getRun(runId)`、`subscribeRun(runId,onEvent)`、`cancelRun(runId,expectedVersion)`、`disposeContext()`、`snapshot(runId)`。`subscribeRun`返回只关闭本地读取的unsubscribe函数，不发送cancel。这些是前端函数，不增加HTTP接口。
2. JSON 请求复用 `businessAssistantRequest` 的 Cookie/CSRF/当前门店守卫；SSE 使用 fetch GET+ReadableStream，显式带同源 Cookie、`X-App-Request`、`X-Store-ID`，不采用不能携带所需 header 的裸 EventSource。只请求固定 `/api/business-assistant` 路由。
3. 每个run内存记录`{view,lastAppliedSeq,displayRevision,connectionState,controller,contextEpoch}`；所有回调先验证当前`businessAssistantContext()`和generation。相同seq/小于已应用seq忽略；缺口先关闭当前订阅，再用同一GET events的after_seq补读至连续。消费run.progress时采用共同payload，必要时GET RunView读取display.text/revision，不另设message快照协议。
4. 网络中断仅将连接置 `reconnecting`，保持 Run 当前已知状态；1/2/5 秒依次重连，之后每 15 秒只做状态读取/事件重连。后台标签页暂停高频刷新，回到可见时立即重新读取。不要因 SSE 断开 POST 新 Run。
5. terminal Run仍需读一次session，取得完整回复与卡片，关闭该run的实时订阅。409先GET RunView/session并核对共同schema所指原因，不能自创cursor错误分类。401清理上下文并交原登录流程；403/404停止读取，不无限重连；500/网络失败显示连接问题，不伪造Run failed。
6. SSE 半截 data/非法 JSON 不提交应用状态；大小限制沿用现有响应保护，异常后重新 GET。Run succeeded 的中文显示固定为“本次准备已完成”，不能使用“业务已完成”。

**状态转移**：本地订阅未连接→读取→连接中断→同一Run重连；Run只按服务端queued/running/succeeded/failed/cancelled展示。终态读回session后关闭订阅；dispose只清本地状态，不产生服务器取消或授权变更。

**异常路径**：半截SSE/非法JSON不应用；序号缺口按after_seq补读，重复事件忽略；401清会话，403/404终止旧读取，409读回核对，网络错误保留已知状态。任何异常均不创建新Run或猜测业务成功。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.1`。

**逐条验收**：

- [ ] 重复/乱序/缺口事件得到与完整顺序相同的状态，display.text按revision替换而不重复拼接。
- [ ] 断线重连使用 after_seq；不存在第二次 POST /runs，unsubscribe/dispose 不调用 cancel/followup。
- [ ] 切店后迟到事件不能修改新门店状态；401/403/404 不继续拉取旧私有数据。
- [ ] 真实 HTTP SSE 连接携带正确 Cookie/门店头；失效 CSRF不能创建 Run。
- [ ] 旧助手发送/确认行为未接新客户端，本项回归仍通过。

<a id="m6-2"></a>

## M6.2：将发送、恢复和显式停止接入持久 Run

**状态**：implemented（2026-09-28 实现并完成外部实测）

**全局顺序前置**：M6.1 done（CP-14 已放行后续编码）。

**验证状态**：Node 行为 + 接线/边界实测通过；真实浏览器双击发送/断线刷新/窄屏布局属 M6.3/M8.4。

**执行记录**：2026-09-28 改 `web/businessassistant.js`：新增 `businessAssistantSendRuntime()`、`businessAssistantSendLegacy()`（原流式逻辑原样保留）、`businessAssistantRuntimeFeatures()`、`businessAssistantWatchRuntimeRun()`、`businessAssistantResumeRuntimeRun()`、`businessAssistantReleaseRuntime()`、`businessAssistantStopButtonHTML()`、`businessAssistantRunText()`；`businessAssistantSend()` 按 `/workspace` 投影的 `features.runtime` 分派，读取失败不得改走另一入口重发；只在员工发送时创建 session，`retry={session_id,request_id,content,thinking}` 保留同一提交标识，202 后用 RunView.id 订阅；只清除与已提交内容完全一致的输入；`businessAssistantWorking()` 在运行期间按服务端事件显示进度（局部发送结束不等于 Run 结束）；停止按钮仅在 `allowed_actions` 含 cancel 时显示"停止本次准备"，点击按当前版本 `cancelRun`，409 只刷新不重放、不删卡；离开页面/退出/换店只关闭订阅并 `disposeContext()`（注释已更新，不 cancel、不 revoke）。未改原确认/批量/卡片有效期/后端/迁移/模型合同。外部套件 `V/tests/frontend/test_m6_2.cjs`（9 项）+ `V/tests/runtime/test_m6_2.py`（7 项），run `20260928T105949Z-6203423841` passed；同指纹复跑 M6.1（`20260928T105921Z-9b6ab23df4`）passed，其"只有客户端自己可取消/清理"边界随本项移动（允许助手工件页发起显式停止）。详见 `docs/implementation-checkpoints/M6-2-review-v1.md`。源码指纹 `ad4d64645b5375f0c1d3aaeb61c569ebff1f85713adba3b08ebe9f6dc720387a`。


**目标**：员工发言产生一个可恢复 Run，关闭页面不会等于取消；明确“停止本次准备”才调用取消接口。

**依赖**：M6.1、M5.1、M5.2、M5.3 的 features 投影。

**先读**：`web/businessassistant.js`的`businessAssistantSend()`、`businessAssistantTask()`、`businessAssistantReconcileRequest()`、`businessAssistantCompose()`、`businessAssistantContinue()`及stop事件分支；`web/businessassistantfiles.js`中调用`businessAssistantSend()`的发送入口；原session/旧消息API。

**允许写**：`web/businessassistant.js`、`web/assistantruntime.js`；必要的文件发送接线；外部 M6.2 两类测试。禁止更改原确认、卡片有效期、批量执行策略；禁止读取或保存员工 Cookie 作为后台授权。

**具体改法**：

1. 抽出`businessAssistantSendRuntime()`；当workspace合同`features.runtime=true`时由`businessAssistantSend()`调用它，否则保留原消息兼容分支。后端明确关闭新功能才能选旧入口；网络错误不得改走另一个入口重发。
2. 仅在员工发送时创建缺失的session。创建Run前沿用并保存内存`retry={session_id,request_id,content,thinking,entry_context?,plan_id?}`，收到202后以RunView.id登记运行。202丢失时重复同一body/request_id，只允许服务器复用；不生成新request_id，不额外发送expected_version。
3. 202表示输入已接收，清除与已提交内容完全一致的输入文字，新的员工输入不清除；保留提交记录供恢复，不把网络unknown当“还没发出”。刷新后使用SessionView.last_request.run_id读取对应Run，null不创建Run；不能依赖丢失的浏览器内存或按消息位置猜run_id。
4. 局部更新进度、文字及完成后的 session，不再用 `businessAssistantTask` 的 finally 将连接结束误写为运行结束。旧卡提交仍用该原确认包装，两个生命周期分开。
5. 将停止按钮文案改为“停止本次准备”，仅当RunView.allowed_actions含cancel时显示；点击`cancelRun(id,version)`提交`{expected_version:version}`，本地进度提示“正在停止”，运行状态仍以服务端为准。409刷新RunView但不重放；取消失败保留运行展示和错误，不把已有卡删除。
6. 离开助手页只关闭/降频订阅。`clearBusinessAssistantSession()` 和退出/换店清理只清浏览器状态，不调用 cancel、更不 revoke Grant；修改现有“退出就是停止”的过时注释。即时Run是否停止由后端会话校验决定，授权跟进退出后继续。
7. 文件“发送资料并填表”继续调用同一个 `businessAssistantSend()`；手工明确点击“查询下一步”仍发送只读意图，未开启 Grant 时确认后只刷新原状态、不发新模型请求。

**状态转移**：未发输入→明确发送→202关联Run→订阅服务端状态→读回最终session；发送结果未知时保留同request_id重试记录。显式停止→提交当前version→以服务器cancelled为准；关闭页面只退出本地订阅。

**异常路径**：202丢失重复原请求，409不换request_id重放；刷新时last_request.run_id为null不猜Run。取消失败保留卡与运行状态；切店/退出丢弃迟到响应。runtime明确关闭走原消息路径，网络失败不自行换入口再发。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.2`。

**逐条验收**：

- [ ] 双击发送、202响应丢失重发、断线刷新同一输入都只出现一个 Run。
- [ ] 新发言、文件发送、明确只读续查走同一 Runtime；页面加载不创建session/Run。
- [ ] 关闭 SSE/切换页面不取消 Run；停止按钮确实 POST cancel，且已生成卡保留。
- [ ] Run成功不等于卡成功；准备结束仅显示真实卡片和原结果。
- [ ] 运行中的草稿/新输入不被迟到完成响应清空，模型截断不产生半截卡片。
- [ ] Grant已开启时退出后 worker继续；即时Run失去登录后按服务端拒绝，浏览器不补造授权。

<a id="m6-3"></a>

## M6.3：实现真实事项侧栏与两列工作台

**状态**：implemented（2026-09-28 实现并完成外部实测）

**全局顺序前置**：M6.2 done。

**验证状态**：Node 行为 + 接线/响应式实测通过；真实浏览器 390/768/1440px 与 IME 焦点属 M8.4。

**执行记录**：2026-09-28 新增 `web/assistantworkspace.js`（唯一出口 `globalThis.AssistantWorkspace`：load/mount/renderSidebar/openItem/patchCurrent/disposeContext/snapshot）与 `web/assistantworkspace.css`，`web/index.html` 在 `assistantruntime.js` 之后接入两者；`web/businessassistant.js` 的 `businessAssistantWorkspace()` 改为 `.ba-runtime-workspace`（280px 事项栏 + 当前事项），当前事项固定 `#ba-current-heading → #ba-current-plan → #business-assistant-messages → #business-assistant-cards → #business-assistant-form`，工作台从卡片队列移入当前事项，并新增 `businessAssistantWorkspaceModule()` 接线：页面绑定后 mount、载入投影、切店/退出随 `businessAssistantReleaseRuntime()` 一并 dispose。侧栏只读 `GET /workspace`，与模型开关无关；固定三组顺序与服务器计数、分项计数；读取失败显示错误而不是空列表；翻页按稳定 key 去重追加；`openItem` 对草稿/重试/运行中/待确认卡拒绝切换，原生待办只查看不创建会话。未改原业务 API、任务分派规则、原十模块样式与确认语义。外部套件 `V/tests/frontend/test_m6_3.cjs`（10 项）+ `V/tests/runtime/test_m6_3.py`（6 项），run `20260928T110717Z-0b9a8fa7d6` passed；同指纹前端回归 6 项（workboard/r3/ux/oneclick）`diagnostic_passed`（`20260928T110759Z-85acdf2e93`）。详见 `docs/implementation-checkpoints/M6-3-review-v1.md`。源码指纹 `b74d59744212ca1635b081791a87387e61f56b8df39e9a2a833cfa6e02b1d427`。


**目标**：把原本人任务、卡片和持续跟进在助手内集中展示，将确认卡移入当前事项，不改变其执行语义。

**依赖**：M6.2、M5.3。

**先读**：`web/businessassistant.js`的`businessAssistantHTML()`、`businessAssistantWorkspace()`、`businessAssistantCardsPanel()`、`businessAssistantQueue()`、`paintBusinessAssistant()`、`paintBusinessAssistantCards()`、`businessAssistantQuestionInput()`；`web/businessassistantwork.js`的`businessAssistantWorkHTML()`、`businessAssistantRefreshWork()`；现有三个CSS的`.ba-*`布局。

**允许写**：新建 `web/assistantworkspace.js`、`web/assistantworkspace.css`，接入 `web/index.html`；改上述助手渲染函数，外部 M6.3测试。禁止改原 business API、任务分派规则或原十模块样式。

**具体改法**：

1. 暴露 `AssistantWorkspace.load({group?,cursor?})`、`mount()`、`renderSidebar()`、`openItem(key)`、`patchCurrent()`、`disposeContext()`。GET workspace 的状态与错误独立于模型配置；模型未就绪时照样渲染本人待办和原页面链接。
2. 侧栏固定“待我处理、跟进中、已结束”；只按服务器 groups 展示。显示分项计数，例如“业务待办 3、待确认操作 2”，不显示错误合计。翻页以稳定 key 去重追加；不得按标题合并两个客户。
3. 当前事项结构固定为 `#ba-current-heading`、`#ba-current-plan`、`#business-assistant-messages`、`#business-assistant-cards`、`#business-assistant-form`。原卡ID、组key、data-ba动作选择器继续有效；确认卡在当前事项流中，通过逐张导航和同组批量核对展示。
4. 自己的 session/plan item：加载原 session，选定 plan，再显示其真实卡。只有原 task 的 item：显示任务摘要、原业务按钮与“交给助手”；点查看不会创建会话。历史对话继续可检索打开，不能只保留有计划的会话。M6.5守卫尚未完成时，openItem检测draft/retry/运行中/未处理卡便拒绝切换并保留当前页，不能在中间里程碑先允许覆盖。
5. 后台事件只 patch 对应显示节点。正聚焦的 textarea、补填input/select节点不替换；卡状态已被他处处理时保留可见补填文字但禁用提交，显示“内容已变化，请核对”，直到员工主动重新加载/切换。不得把过期答案提交到新proposal。
6. 在`.ba-runtime-workspace`根下覆盖旧两列聊天/卡片样式：桌面事项栏宽280px，内容`minmax(0,1fr)`；严格按PROJECT_SPEC，视口小于1024px事项栏抽屉化，小于768px当前事项单列。验390/768/1440px及1024边界，输入区随工作台底部固定，卡片不盖住确认区。
7. 初次进入不自动选并发送推荐；无当前事项时欢迎页+真实侧栏。全局切店/退出调用两个模块dispose，移除抽屉遮罩和监听器；同一mount不得重复绑定事件。

**状态转移**：工作台未加载→GET授权投影→按服务端分组显示；选中事项只改变当前展示，后续服务端事件局部更新。切换到窄屏只改变抽屉布局，切店/退出销毁当前投影；不在前端推进Plan/Task/Proposal。

**异常路径**：workspace失败显示读取失败和原人工入口，不能冒充空列表；无权限项不展示。旧卡被他处处理时禁用旧提交并保留可见编辑文字；草稿/重试/忙事项未获明确切换选择时保留原页；焦点和IME输入不能被状态刷新重建。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.3`。

**逐条验收**：

- [ ] 三组排序和分项计数等于服务器，重复task仅在服务器证明同一task_id时合并。
- [ ] 私人聊天、另一门店卡片及不可读原单不出现；失败读取不显示为空列表。
- [ ] 真实任务点击原页面仍可办；历史无计划会话、旧卡可读。
- [ ] 页面只有主导航、事项栏、当前事项；不存在额外常驻卡片列。
- [ ] 中文输入、鼠标选区、IME、补填焦点经20条状态事件仍不丢，选择按卡ID稳定。
- [ ] 390/768/1440像素下输入/确认/侧栏可达，键盘可开关抽屉并恢复焦点。

<a id="m6-4"></a>

## M6.4：默认进入助手，同时保持原人工导航与深链接

**状态**：implemented（2026-09-28 实现并完成外部实测）

**全局顺序前置**：M6.3 done。

**验证状态**：Node 行为 + 接线/回归实测通过；真实浏览器落地与深链接刷新属 M8.4。

**执行记录**：2026-09-28 在 `web/app.js` 新增唯一判定 `assistantDefaultRoute({store,features})`（`store==='all'`→`analytics/overview`；`features.home===true`→`business-assistant`；否则 `work`）及 `assistantFeatures()`/`loadAssistantFeatures()`/`bootDefaultRoute()`；`boot()` 保持鉴权与首次改密门禁最优先，随后仅在没有有效 hash 时读取 `/workspace` 决定默认页；门店切换与失败恢复、`hashchange` 空 hash 分支全部改用同一判定，删除分散的 `location.hash.slice(1)||'work'`；读取失败或开关缺失时降级回原工作台，登录不因模型/开关失败而失败。导航顺序改为业务助手、我的工作、快捷操作，其余原入口与角色条件保留。欢迎页改为 `businessAssistantWelcomeExamples()`：取自发布 `workflow-guides.json` 与 `UX_COMMON_WORKFLOWS` 的交集、按 `canEnter` 与岗位过滤、最多 4 个；只读岗位与集团汇总只给 `query_status` 查询示例；目录不可用时退回 4 条只读查询示例；点击只预填草稿（不建会话/不发模型）。未新增助手 hash 语法，原路由与需求映射未删。外部套件 `V/tests/frontend/test_m6_4.cjs`（6 项）+ `V/tests/runtime/test_m6_4.py`（6 项），run `20260928T111826Z-e49f524fa7` passed；同指纹 M6.1/M6.2/M6.3 与前端 6 项检查全部 passed。详见 `docs/implementation-checkpoints/M6-4-review-v1.md`。源码指纹 `52bfeaf425f59001580c3a5f8a35822b23794598abe11bffd347eabba2ba8137`。


**目标**：新助手成为默认工作台；有效业务深链接、首次改密、汇总只读与人工路径保持原语义。

**依赖**：M6.3、M5.3 的 features。

**先读**：`web/app.js`的`state`、`loginPage()`、`boot()`、`switchStore()`、`window.addEventListener('hashchange',...)`、`shell()`、`bootstrapAppOnce()`；`web/workflowcontent.js`暴露的`WorkflowGuides.validRoute()`、`WorkflowGuides.canEnter()`；`web/businessux.js`的`UX_COMMON_WORKFLOWS`；当前模块及发布工作流目录。`app.js`没有名为main的入口函数，不能修改或调用不存在的main()。

**允许写**：`web/app.js`、`web/assistantworkspace.js`、`web/businessassistant.js` 的欢迎示例；外部 M6.4测试。禁止删除原路由、菜单或需求项；禁止在登录过程中自动创建会话、启用Grant或调模型。

**具体改法**：

1. 新建唯一`assistantDefaultRoute({store,features})`：features.home开启时为`business-assistant`；明确关闭时为`work`，集团汇总继续`analytics/overview`。普通门店切换成功及无显式目标的恢复使用该函数，不到处分散替换'work'。四开关初始均false，UI里不得改成true。
2. `boot()` 在鉴权/首次改密门禁后读取workspace开关和必要目录，再确定空hash默认页；合法深链接优先。不以 `WorkflowGuides.validRoute` 的语法通过证明对象可读，仍由原页面API验权。无效语法回默认，语法合法但不可读的具体原单显示原拒绝，不悄悄跳到别的客户。
3. 首次登录必须改密保持最优先。无model配置或workspace暂时读取失败：进入可降级助手壳，提示读取错误、给原`work`和十模块入口；不因为模型失败登录失败。明确开关关闭才回旧首页。
4. `shell()`导航顺序改为业务助手、我的工作、快捷操作；其余原评审/统计/指引和十模块按钮及角色条件保留。
5. 欢迎页最多4个岗位相关示例，从现有发布workflow目录及`UX_COMMON_WORKFLOWS`交集选择，按真实可进入权限过滤。示例只预填；readonly岗位显示查询示例，集团汇总不提供写示例。不能继续给每岗位统一“建立车型目录”等5个写操作。
6. 本项不新增助手session/plan hash语法；保留`#business-assistant`。侧栏通过已验证引用选事项，原单深链接完全沿用原路由。

**状态转移**：鉴权→首次改密门禁→读取开关/当前门店→有效深链接或默认路由；home开启且无有效深链接才进助手，明确关闭回work，集团汇总回analytics/overview。欢迎示例点击只预填，不创建会话/Run/Grant。

**异常路径**：非法路由回默认；合法但不可读原单保留原拒绝，不跳到别的对象。模型未配置或workspace失败保留可降级助手壳与人工入口；无门店、门店撤权、换店失败沿原守卫，不绕过改密和授权。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.4`。

**逐条验收**：

- [ ] 无hash登录/已登录刷新默认助手；有效原单、任务、流程深链接不被抢占。
- [ ] 首次改密先完成改密；汇总仍只读；无门店/撤权按原服务拒绝。
- [ ] 开关关闭回旧首页，模型未配置仍显示原待办及原业务入口。
- [ ] 首页GET读取之外，session创建、Run创建、followup、业务写请求均为0。
- [ ] 十模块全部原入口及193原需求名仍能找到，111目录无静默删项。
- [ ] 最多4个相关示例，点击预填不外发，无权限写入口不变可点。

<a id="m6-5"></a>

## M6.5：统一交接守卫与原单/任务/流程“交给助手”入口

**状态**：implemented（2026-09-28 核心与按钮面全部实现并完成外部实测）

**全局顺序前置**：M6.4 done。

**验证状态**：核心交接入口、守卫、内存态、表单保护与四个原页面按钮面实测通过；真实浏览器点击/跳转属 M8.4。

**执行记录**：2026-09-28 在 `web/assistantworkspace.js` 新增唯一交接入口 `requestHandoff({entry_context|reference+intent,prompt?,contextEpoch?,returnRoute?,keepCurrent?})` 及 `guardHandoff/pendingHandoff/clearHandoff/handoffLabel/buildEntryContext/routeValid`，并新增仅内存的编辑态 `uiBySession`（`rememberUi/restoreUi/clearUi`，含草稿/答案/选卡/过滤/计划/文件选择，临时键 `new`，切店退出清空）。`web/businessassistant.js`：`new`/`session` 入口改走 `businessAssistantSwitchMatter()`（统一守卫 + “留在当前事项 / 保留当前事项并打开”）、新增 `businessAssistantNewMatter()` 与 `businessAssistantHandoffBar()`，发送时把 `entry_context` 放进 Run 提交体并在服务器接收后清除标签。`web/workforms.js` 新增 `workFormRequestHandoff(dialog,onDiscard)`（提交中拒绝、单实例提示、只有明确放弃才关表单并交接一次）。`web/workflowguides.js` 的 `applyWorkflowAssistantIntent()` 不再直接 `session=null`，改为薄包装调用交接入口并携带 `workflow_id`。实测发现并修复 3 处前端缺陷：`report_query` 引用类型/ID 种类未按服务器合同区分、`returnRoute` 未做字符串校验、二次交接被自家守卫误拦（未改动的预填草稿应允许改交接目标）。外部套件 `V/tests/frontend/test_m6_5.cjs`（11 项）+ `V/tests/runtime/test_m6_5.py`（6 项），run `20260928T112532Z-571cad4490` passed；同指纹 M6.1—M6.4 与前端 6 项回归全部 passed。按钮面（PATCH-M6-5-02/03）：handoffButton/parseRef 共用实现 + 原待办行、原单页、moduleCard、快捷操作卡接入（各页面模块自带薄封装以免离线单文件加载报错），外部套件增至 13+8 项并复跑通过；通知入口仍属 M6.7。详见 `docs/implementation-checkpoints/M6-5-review-v1.md`。源码指纹 `81e6abc74ead15aaafbf4cf0a85c2b401e3a2a4b78c77cefeae867873e784802`。


**目标**：所有业务入口带真实引用进入助手，不覆盖草稿、卡片答案和未完成原表单，不隐式取消运行。

**依赖**：M6.3、M6.4、M5.1对entry_context的校验。

**先读**：`web/workflowguides.js`的`workflowAsk()`、`applyWorkflowAssistantIntent()`、`workflowNavigate()`；`web/workforms.js`的`workFormCloseRequest()`、`enhanceWorkForm()`；`web/businessux.js`的`uxCurrentCase()`、`mountBusinessUX()`；`web/moduleworkspaces.js`的`moduleCard()`、`moduleTaskRows()`；`web/app.js`的`workPage()`；`web/businessassistant.js`的new/session/suggestion事件分支。

**允许写**：上述入口文件和`web/assistantworkspace.js`；外部M6.5测试。禁止把员工未发送表单值自动外发，不根据DOM标题解析业务ID，不从模型推荐文本构造URL或命令。

**具体改法**：

1. 固定唯一前端函数`AssistantWorkspace.requestHandoff({entry_context,prompt,contextEpoch,returnRoute})`。entry_context遵循M5.1共同DTO，意图仅query_status/explain_prerequisites/prepare_action；prompt来自发布workflow模板或对应三种固定中文模板。returnRoute只用于返回原页面，必须经原路由校验，绝不发给工具执行。
2. 用真实`state.row`/task记录和服务器object_ref建引用；通用Case用注册`case`对象，专用对象必须使用后端返回的受评审type。拿不到明确引用时只保留原业务入口，不猜ID。前端用户/店标识仅作contextEpoch迟到保护；服务端仍重新读取所有事实。
3. 未完成原modal表单：不另开同一个#modal覆盖表单；在`workforms.js`新增`workFormRequestHandoff(dialog,onDiscard)`，复用`workFormStates`的dirty/submitting/lastControl，在原表单插入提示“继续填写 / 放弃后打开助手”。提交中禁止跳转；员工点放弃才清dirty、关闭并执行一次保存的临时handoff。继续填写删除提示并恢复原焦点。回调再次校验contextEpoch；每个modal只能保留一个handoff提示，第二次点击不覆盖第一次待决定意图。
4. 统一`guardHandoff`也覆盖new/session/history/suggestion/notification入口。当前draft或retry未核对时停留原事项，明确提示先处理，禁止替换。当前有pending/executing/uncertain卡或运行时，显示“留在当前事项 / 保留当前事项并打开”；后者保存本会话内存编辑状态并打开目标，不cancel、不重生成卡。
5. 为允许的显式切换建立内存`uiBySession`，保存`draft/answers/activeCardId/queueFilter/workPlanId/files选择状态`；新事项临时key为`new`。不复制到其他会话、不落浏览器存储；切店/退出清空整个map。回到旧session重新读取服务器卡，再仅恢复相同proposal_id的答案。
6. 替换现有`workflowAsk()`、`applyWorkflowAssistantIntent()`里直接session=null的路径；它们成为统一入口薄包装。原待办、原单、moduleCard、快捷操作及流程文章加按钮；模块/快捷入口传共同DTO的工作流引用，原任务传任务引用，原单传对象引用，禁止发明另一组线上字段。
7. 交接成功只展示上下文标签并预填，entry_context随下一次员工发送提交；取消或改为独立新事项时清掉标签。换店/退出/contextEpoch改变时立即丢弃待交接内容。错误或未知对象不给出“已办理”。

**状态转移**：入口点击→核验引用/上下文→检查原表单与当前助手编辑→明确选择→仅预填；员工后续发送才提交entry_context。保留旧事项切换只改变内存选中项，不cancel、不revoke；切店/退出清空交接与答案缓存。

**异常路径**：原表单提交中拒绝跳转；dirty表单只允许继续或明确放弃。缺真实对象引用、过期contextEpoch、权限失效时保留原入口；重复handoff不覆盖第一次待决定意图，草稿和待核对retry不静默替换。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.5`。

**逐条验收**：

- [ ] 五类入口都调用唯一requestHandoff，payload无自报员工/门店/角色/任意URL。
- [ ] 原表单继续填写值/焦点全保留；只有明确放弃才关闭，提交中不能跳转。
- [ ] 草稿/重试不覆盖；旧卡和答案经显式保留切换可返回，运行没有cancel请求。
- [ ] 原workflow入口不再无条件清当前session；批量卡选择仍按ID。
- [ ] 交接点击模型/Run/业务POST数量均为0；员工发送才提交一个Run。
- [ ] 专用对象不误当Case；同名/错店/撤权引用由服务器拒绝，迟到响应不可复活旧上下文。

<a id="m6-6"></a>

## M6.6：每件事的持续跟进与生命周期控制

**状态**：implemented（2026-09-28 实现并完成外部实测）

**全局顺序前置**：M6.5 done。

**验证状态**：Plan 投影、显式生命周期动作、冲突/权限/失败分支实测通过；退出后 worker 继续与真实浏览器反馈属 M8.1/M8.4。

**执行记录**：2026-09-28 在 `web/assistantworkspace.js` 新增 `loadPlan(planId)`（只读 `GET /plans/{id}`）、`setFollowup(action)`（`POST /plans/{id}/followup`，只提交当前 `plan.id` 与当前 `expected_version`）、`planHeaderHTML()` 与 `planStatusText/grantStatusText/followupAllowed`：事项头部显示目标、固定中文状态（进行中/已暂停/已完成/已取消、尚未开启/持续跟进中/已暂停跟进/已结束跟进）、`grant.stop_reason` 与前三条等待原因；enable 前显示六要素范围说明（目标、门店、本人身份只查询与准备、实际办理需确认、退出后继续、可暂停或结束），默认无预选勾；pause 保留卡并以返回 PlanView 为准；revoke 文案「结束这件事」需二次确认且明确不取消原业务，从不发送 `completed`；409 不重放并读回当前计划（提示在读回后仍可见），403/404 收起写控制并提示原页面仍可办理；`features.followup` 关闭时只显示状态不渲染按钮。`web/businessassistantwork.js`：确认/取消卡与切换计划只触发 `bawLoadPlan(planId)` 重新读取，离线单独加载时退化为空操作；`web/assistantworkspace.css` 仅追加 `.ba-plan-*`。实测发现并修复“409 提示被随后的成功读回清空”一处产品缺陷，并把 M6.3 的导出合同改为集合包含式以免后续里程碑扩充导出面误伤。外部套件 `V/tests/frontend/test_m6_6.cjs`（12 项）+ `V/tests/runtime/test_m6_6.py`（7 项），run `20260928T115324Z-7f746aa3fb` passed；同指纹 M6.1—M6.5 与前端 6 项回归全部 passed。详见 `docs/implementation-checkpoints/M6-6-review-v1.md`。源码指纹 `ac19fbc8d8a1d5df54ba920bc312a61bca5d043cb357d49e7e346791358e5ff3`。


**目标**：员工明确授权当前事项，能看见何时等待自己/同事/事实，并正确暂停、恢复或结束委托。

**依赖**：M6.3、M6.5、M5.3及后台Grant/条件调度已经通过其前置验收。

**先读**：`web/businessassistantwork.js`、`web/businessassistant.js`的`businessAssistantContinue()`、`businessAssistantAutoContinue()`；`app/assistant_runtime_schemas.py`、`app/assistant_runtime_plans.py`的Plan/Grant合同。

**允许写**：`web/assistantworkspace.js`、`web/businessassistantwork.js`、限定CSS、必要的原stop/continue文案；外部M6.6测试。禁止前端定时调模型、根据文字/时间自行成卡或启用Grant。

**具体改法**：

1. `AssistantWorkspace.loadPlan(planId)`读取PlanView，在当前事项头部显示goal、status的固定中文翻译、grant.status/stop_reason及共同steps DTO的等待原因。旧计划由服务端投影可读steps和allowed_actions；首次enable由服务端核验并升级，UI不自己判断engine_version或改旧steps。feature关闭的旧页面继续已有work-status读取，不要求新PlanView增加字段。
2. `AssistantWorkspace.setFollowup(action)`仅提交当前plan.id及当前version；按钮来自allowed_actions，features.followup关闭时显示已有状态但不伪造可操作按钮。
3. enable前在当前事项内显示范围说明：当前目标、门店、本人、只查询和准备、实际办理需确认、退出后继续、暂停与结束入口；按钮“开启此事项持续跟进”完成明确一次授权，默认没有预选勾。resume要重新展示当前目标和退出后继续语义，员工明确点击恢复。
4. pause保留已生成卡，状态以返回PlanView为准；revoke按钮文案“结束这件事”，二次确认说明“不取消原业务/已有记录”，明确点击才提交。不得将“结束”标为业务完成，也不能前端发送completed。
5. 409版本冲突不重放动作，重新GET plan并提示目标/权限可能变化，用户重新核对。403/404停止展示可写控制，不修改旧授权快照；权限恢复需新有效会话/事项时显示服务器原因和原业务链接。
6. 确认或取消卡后仅触发workspace/plan读取；后台有active Grant才决定是否准备下一步。卡取消→依赖等待，过期→等待员工重新核对，uncertain→需核对，不在UI自动retry。
7. 退出只清前端；不得在logout链路调用followup pause/revoke。登录回来读服务器授权和卡片，而不是从本地bool恢复。grant完成/撤销原因使用服务器stop_reason显示。

**状态转移**：首次明确enable才获得Grant；pause后保留卡并停止跟进，resume重新验权，revoke结束助手目标。Plan只按根合同active/paused/completed/cancelled展示，Grant只按active/paused/revoked展示；终态不由UI重开，Run停止与Grant生命周期分开。

**异常路径**：409读回当前Plan并要求重新核对，403/404收起写控制；旧计划缺可验证条件时显示服务端所需补齐内容，不解析wait_for自动升级。过期卡等待员工显式重新准备，取消卡阻塞依赖，uncertain先核对；开关关闭或logout均不伪造新授权。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.6`。

**逐条验收**：

- [ ] 新事项默认没有Grant；展示控制本身不触发POST。
- [ ] 仅显式enable/resume开启；每次带准确expected_version，重复点击不可绕过冲突。
- [ ] pause保留卡，revoke结束助手委托不取消原单；停止Run与暂停Grant是两个不同按钮。
- [ ] 退出后授权跟进可生成真实待确认卡，再登录能看到；没有自动业务确认。
- [ ] 未授权事项确认后不自动续办；取消、过期、结果不明、权限失效显示准确等待原因。
- [ ] 中文UI不显示租约/token/工具调用ID，不把无待办和Run成功说成目标完成。

<a id="m6-7"></a>

## M6.7：站内通知、原任务协作和未知结果核对

**状态**：implemented（2026-09-28 实现并完成外部实测）

**全局顺序前置**：M6.6 done。

**验证状态**：通知投影/轮询/点击已读、协作引用与回执核对实测通过；真实浏览器与真实事件流属 M8.1/M8.4。

**执行记录**：2026-09-28 在 `web/assistantworkspace.js` 新增 `loadNotifications/startNotifications/stopNotifications/pollTick/onVisibility/invalidateNotifications/openNotification/checkReceipt/receiptText/notificationPanelHTML/receiptButtonHTML`：未读计数取 `NotificationList.unread_count`，列表只用 `safe_summary`/`created_at`/授权引用，稳定 `id` 去重、`next_cursor` 原样透传、不按摘要拼路由；可见页每 30 秒轮询、隐藏停止、回前台立即读取、切店/退出停轮询并清缓存，既有运行事件只触发一次合并读取且未新增事件类型，只在通知首次出现时轻提示一次；点击通知先按引用打开目标（任务走统一守卫、会话按引用切换、其余只见原 `manual_route`）再显式 `POST read`，守卫拒绝或 read 失败不假称已读（提示「已打开，已读状态未更新」）；`核对办理结果` 只 GET 原 `execution-result`，五种结果固定文案，失败保持待核对、不重发业务写、不换 `request_id`；模块内不含 `assignDialog`/`state.row` 等代理动作，评审引导只消费服务端结果字段。`web/assistantworkspace.css` 追加 `.ba-notice-*`。实测发现并修复：新增轮询把 M6.3/M6.5/M6.6 的 Node 替身挂死（真实 30 秒定时器占住事件循环），三套替身改为记录式定时器；M6.6 的“禁止前端定时器”按计划收窄为“定时器只用于通知轮询”。外部套件 `V/tests/frontend/test_m6_7.cjs`（11 项）+ `V/tests/runtime/test_m6_7.py`（9 项），run `20260928T121421Z-ba5b526aa9` passed；同指纹 M6.1—M6.6 与前端回归全部 passed。详见 `docs/implementation-checkpoints/M6-7-review-v1.md`。源码指纹 `e04af80248373abb5459737ffd50d5e0bf99f8abc4b780d9583b718d448cc3d6`。


**目标**：重要变化可见且可恢复，不复制同事私聊；通知与执行结果不会覆盖员工当前工作。

**依赖**：M6.5、M6.6、M5.4、M5.1执行结果接口、M2.2真实refusal分类及M4.9结果恢复。

**先读**：`web/app.js`的`taskList()`、`workPage()`及`a==='assign'`分支；`web/businessassistant.js`的`businessAssistantDecide()`、`businessAssistantConfirmCards()`、`businessAssistantDisplayStatus()`；通知和execution-result后端schema；`web/escalations.js`原评审入口。

**允许写**：`web/assistantworkspace.js`、`web/assistantruntime.js`、有限助手卡与topbar接线、外部M6.7测试。禁止改原转交接口/收件岗位、共享会话、把通知已读当完成、调用MCP确认/授权。

**具体改法**：

1. 在助手事项栏顶部放站内通知入口，未读计数使用NotificationList.unread_count；面板使用safe_summary、created_at和当前授权引用，不要求title/summary等字段别名。next_cursor仅原样传给下一页；稳定notification.id去重，不根据摘要拼路由。
2. 可见页面每30秒GET通知，窗口重新激活立即读取；隐藏标签停止轮询，切店/退出dispose。既有proposal.prepared/plan.updated/run.completed/run.failed/run.cancelled事件可使通知缓存失效，合并为最多一次读取；不新增notification_changed事件。只在新通知ID首次出现时给一次轻提示；同页重复刷新不反复toast。
3. 点击通知先按引用通过统一guardHandoff/openItem或原路由打开；guard拒绝/读取失败不假称已读。成功打开后显式POST read；失败显示“已打开，已读状态未更新”，不撤销已打开业务。重复read不影响任务状态。
4. 同事协作任务只显示原权限内负责人和任务状态。接收员工进入自己会话，以本人身份查询/准备；无自己的session_id时不能打开发起人的聊天。需要转交时先走原授权manual_route加载原单，再由原taskList()/a==='assign'分支调用assignDialog(id)。当前assignDialog依赖state.row.tasks，侧栏不得直接拿task_id调用它或自行改写state.row；不新造代理操作。
5. 对executing过久/uncertain卡增加“核对办理结果”读取按钮；只GET原execution-result。confirmed_success显示已找到原成功回执并提供原单；卡状态仍等服务端持久恢复后刷新。not_found/unsupported/inaccessible/mismatch均保留待核对，不启用重试业务写、不换request_id。
6. refusal相关UI只消费服务端可评审标记与真实refusal引用；无记录或rule显示原业务原因，不自行根据HTTP403生成评审建议。业务成功但通知读取/更新失败只给次级提醒，不能修改卡succeeded。

**状态转移**：服务端真实变化产生unread通知→打开目标成功→POST read；resolved仅来自服务器真实事项状态。协作只沿原任务分派；执行结果按钮只读取ReceiptLookup，Proposal状态等待服务端恢复后重新读取。

**异常路径**：重复通知只提示一次；守卫拒绝、目标失权或打开失败不假称已读；read失败保留已打开业务。通知无当前授权目标只显示摘要；回执not_found/unsupported/inaccessible/mismatch保持待核对，不重发业务POST；403无真实refusal不生成评审建议。

**验证命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.7`。

**逐条验收**：

- [ ] 重复事件/轮询同一通知只显示一次；没变化不持续提示。
- [ ] A员工通知/私聊/payload不被B读取；B接手真实任务使用自己会话和权限。
- [ ] 新通知到达、点击被草稿守卫挡住时不覆盖输入/答案，也不误标任务完成。
- [ ] read失败不改变原业务成功；同事转交仍原API审查。
- [ ] 五种execution-result均正确展示，任何路径不重发原业务POST。
- [ ] 禁止自批等rule没有“更高权限”提示；有真实authority/amount refusal才出现原评审引导。

<a id="m6-8"></a>

## M6.8：兼容回归、窄屏与关闭新功能的收口

**状态**：implemented（2026-09-28 收口完成，21 条命令全部通过）

**全局顺序前置**：M6.7 done。

**验证状态**：M6.1—M6.8 两类套件 + 适用旧回归 + 语法检查 + 生成物检查全部通过；真实浏览器/真实模型/PostgreSQL/员工试用留 M8.1—M8.10。

**执行记录**：2026-09-28 定点修复 `web/assistantworkspace.js` 的通知面开关（新增 `notificationsOn()`：`ASSISTANT_NOTIFICATIONS_ENABLED` 关闭或投影未到时隐藏入口、不轮询、不读取、事件也不再触发合并读取），未改其它行为。新增 M6.8 套件 `V/tests/frontend/test_m6_8.cjs`（6 项）与 `V/tests/runtime/test_m6_8.py`（10 项），并新增 runner 适配脚本 `scripts/check_m68_node_syntax.py`（10 个改动 JS 逐个 `node --check`）与 `scripts/check_m68_workflow_guides.py`（镜像内执行 `scripts/build_workflow_guides.py --check`），两者按 runner 契约写出完整 `command-result.json`。M6.8 runner 共 21 条命令：M6.1—M6.8 Node 套件 82 项、适用旧回归（check_ux/check_workspaces/check_assistant_workboard）67 项、M6.1—M6.8 Python 套件 61 项、语法检查 10 个文件、生成物检查 1 项，全部 complete。实测发现并修复：通知面未跟随自身开关（产品缺陷）、helper 未按 runner 契约写报告且误用不存在的环境变量、adapter 一次只接受一个已登记脚本、M6.7 套件需先读取投影。run `20260928T124459Z-6a0277b07c` passed。详见 `docs/implementation-checkpoints/M6-8-review-v1.md`。源码指纹 `2ca563d5433d0c84460d547ab25f35e361871b02c23deeab380ba70589feddb6`。**未完成（不得声称已验收）**：付费真实模型回归（M8.5/M8.6）、PostgreSQL 生产升级与恢复（M8.3）、真实 HTTP 浏览器交互（M8.4）、员工试用（M8.9）、Windows/Linux 实例（M8.7/M8.8）。



**目标**：完成本阶段的兼容与交互验收，证实原人工业务不依赖新Runtime继续可用。此项以检查和定点修复为主，不扩展产品功能。

**依赖**：M6.1—M6.7、M5.5、M0的旧测试依赖恢复。

**先读**：本章完成的7项实施记录；`docs/requirements.json`、`web/workflow-guides.json`、`docs/UI简化-功能验证清单.json`；当前全部助手/入口修改diff；现有打包与静态资源服务路径。

**允许写**：前7项范围内的缺陷修复及外部M6.8测试、实施记录。禁止为了过测删需求、删断言、扩大人工兜底范围，禁止补造旧Grant/卡关联或回滚业务数据。

**具体改法与测试场景**：

1. 四个开关逐一关闭验证：features.home关→旧首页/人工入口；features.runtime关→旧消息/流入口走原会话执行路径，新Run创建503，worker停止新领取及后台准备；followup关→停止新开启且现有状态可读；notifications关→隐藏通知交互、不改业务。实际配置名使用根架构ASSISTANT_HOME_ENABLED/ASSISTANT_RUNTIME_ENABLED/ASSISTANT_FOLLOWUP_ENABLED/ASSISTANT_NOTIFICATIONS_ENABLED。已存在记录保留且按原授权可查，有效旧卡仍可人工确认；重新开启按授权、租约及幂等规则恢复。关闭UI不得发revoke/cancel清理。
2. 仅runtime开启时，原消息JSON、原消息SSE、新Run接口使用相同request_id只关联同一个Run；关闭时验证旧助手原执行路径仍可用。MCP工具仍read/prepare/plan，不新增confirm/followup工具。该项HTTP测试需验证实际状态，不只扫描工具名字。
3. 单卡确认、同组批量逐张提交、失败即暂停、取消不算成功；原后端旧batch继续执行语义保持并单独标明，UI不得改为调用旧batch冒充暂停。
4. 从193需求与111发布workflow逐项验证能找到原人工入口；在有权岗位加载真实目的页，未知/历史业务版本走原通用页。任务筛选先授权再计数分页；不以一个管理员加载通过代表所有岗位可用。
5. 真实HTTP浏览器覆盖390/768/1440、键盘/读屏标记、IME、长内容滚动、焦点、草稿、补填、批量列表、无模型配置、SSE重连、双标签状态变化、换店、退出、同事接手与未知结果。保留合成截图和逐项请求计数。
6. 加载new script/CSS失败时原人工页面仍可用；不会因为ReferenceError导致整个shell白屏。用已版本发布的资源/页面一起更新，不引入独立前端构建。
7. 报告分别列代码/确定性UI/真实HTTP/真实模型/员工试用状态。M6不运行付费真实模型、也不能把合成provider输出算真实模型成绩；后续总计划P12负责真实模型和20%省时目标。

**状态转移**：在合成实例逐项开启/关闭四功能，关闭只停止对应新行为并保留原业务及既有记录；重新开启后按服务器授权/租约/幂等恢复。验收全部通过才将本里程碑in_progress改为done；单次测试passed不代表整体或生产验收通过。

**异常路径**：资源加载失败保留人工页面；无模型、断流、双标签、换店和未知结果均按前述守卫处理。任何回归失败保留失败证据并修复，不能删断言/需求；实际PostgreSQL、真实模型或公司环境不足留后续相应里程碑，不冒称本阶段完成其验收。

**验证命令**：

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M6.8
## workflow生成检查由M6.8 runner在本次安全源码镜像执行
```

M6.8 runner须在当前源码镜像重新执行M6.1—M6.7两类测试及恢复的旧UX/workspaces/assistant-workboard适用回归，并由同一外部venv执行当前镜像`scripts/build_workflow_guides.py --check`；历史脚本需由M0的路径适配指向当前镜像，不直接运行归档目录中会读旧源码的版本。Node语法检查由runner对实际改动JS逐个`node --check`；无package.json，不添加npm检查。

**逐条验收**：

- [ ] 全部M6测试和适用旧回归通过，无新跳过/降低断言；每份证据有当前源码指纹。
- [ ] 四开关单独关闭和组合关闭仍能人工办理，旧记录可读，原业务事实不被清除。
- [ ] 原消息/流式/MCP及手工确认兼容，未确认业务写为0。
- [ ] 193入口映射及111生成检查完整，角色/门店测试有真实HTTP证据。
- [ ] 真实HTTP与三个宽度交互通过，敏感/真实客户资料未进入截图/日志。
- [ ] 收尾记录明确本阶段未完成真实模型、PostgreSQL生产部署与公司员工验收，不复用历史成绩宣称新系统已验收。

## M6 完成后的交付记录格式

每项记录：`ID → 实施状态(todo/in_progress/done/blocked) → 当前源码指纹 → 修改文件 → 已完成验收checkbox → 测试结果(passed/failed/blocked/not_run) → runner完整命令/退出码/证据路径 → 未完成项 → 下一项ID`。记录事实，不写“基本通过”。根协议已经冻结，按ARCHITECTURE F/H实现；实际前置未done或发现根本合同冲突时说明具体证据，不能以自拟协议或mock替代。未开始的后项保持todo；当前项测试失败保持in_progress修复，实际外部条件/未决架构阻断才blocked。单项完成先更新记录，再按主提示词的单次turn/目标模式决定是否继续。这里的实施状态与业务Plan/Run/Proposal原状态严格分开。提交或打包时排除V、合成库、截图、私密配置；业务仓库仅保留正式源码与实施文档。

## M7 业务对象适配：按单一适配器执行的实施章节

编写依据：当前 `total_plan.md` 与只读源码检查。共 12 组、52 个可独立验收的小项；组标题不计任务状态。本文是实施要求，所有复选框均未验收。本次没有运行历史测试、接触公司库或修改业务源码。

## 全部 M7 小项共同遵守的合同

1. 所有 M7 小项共同依赖已验收的 M6.8，并严格按本文编号的数字顺序串行实施：首项 M7.1.1 依赖 M6.8，其后每项同时依赖 M6.8 与本文中紧邻它的前一个小项；例如 M7.2.1 依赖 M7.1.3，M7.10.1 依赖 M7.9.6。组标题不是任务，不按字符串字典序排序。先完成主计划指定的运行时模型、内部身份、通用工具、条件、准备幂等、回执读取与 WakeEvent 基础。每次只实现下方一个完整编号，不一次横扫全部领域；正文引用的现有 API/service/models 必须逐个打开，不能按业务名称猜流程。
2. 接口固定为 `DomainAdapter.read_snapshot(principal, ref)`、`extract_result(operation_id, response)`、`read_receipt(principal, submission)` 与注册的 `fact_snapshot`。使用 ARCHITECTURE 定义的返回类型，不创建另一套 Runner/状态枚举/权限代码。快照没有原生版本时 `native_version=null`，不得捏造版本、使用读取时间假装原版本。
3. `read_snapshot` 只能通过受评审的原授权 GET/共享只读查询取得对象；不直接越过原页面岗位规则扫描业务 ORM。接入原 service 的目的仅是理解事实来源和摘要，不从 adapter 调用业务 command/execute。只读回执经统一 receipt resolver，以冻结提交的 operation、原 request_id、actor、store、原生 digest 查准原回执，并重新验原结果可见性。
4. `extract_result` 必须按准确 operation_id 和已校验原响应识别类型。这里的 operation_id 是原 gateway 定义的 `METHOD + 空格 + route.path`，不是 OpenAPI 自动生成的函数名（证据：`app/business_assistant_gateway.py:137-160`）。M0 在隔离源码镜像中扫描实际 FastAPI 路由注册及 `app/business_assistant_capabilities.json`，按原 `_operations()` 规则登记可用目录：写操作须在 reviewed catalog 内，GET 仍受原 domain/closed/denied/body 等过滤和调用时授权；原路由存在不等于助手获准准备。每个小项第一步须从该目录及其原 API/schema 核对并写出本 adapter 的确定映射表（用途 snapshot/result/receipt、完整 operation_id、精确 path_args、原响应类型、原回执族）。保留 `{key}`/`{case_id}` 等原占位名；例如维修详情是 `GET /api/repair-orders/{case_id}`，销售报价详情是 `GET /api/sales-quotes/orders/{key}`。列表中未登记或运行时不存在的 operation 明确拒绝并报告能力缺口，不让模型猜 ID，不扩大 reviewed catalog。fixture 必须断言映射都能在当前目录中解析、错误 operation 被拒绝。返回不同对象时显式声明关联，不把所有字段名为 id 的数值都当 case_id；不能从助手文字、页面标题或前端路由猜编号。缺必要 ID 返回无法建立依赖证据；原调用成功结果本身保持不变。
5. `fact_snapshot` 只投影本项列出的原事实，保留原对象引用、原版本、来源记录 ID、观察时间及单位。禁止通用 JSONPath/表达式/SQL/状态修改器。不同 native version 必须走原 `flow_version` 对应读法；未知版本给原页面入口，不能造业务状态。
6. 原 API 的动作展示不统一：带真实 enabled/reason 的结果可以保留；仅有岗位筛选字符串列表时，不能当作所有业务条件已验证。每项 available_actions 统一使用 availability=enabled|disabled|unknown；不得仅因名字在列表里满足 native_action_available 条件。可调用的原纯只读守卫优先复用；没有纯只读证明就返回 unknown，不得试调写接口。对承诺自动续办链仍无法证明条件的缺口须报告，不能标成已支持；确认仍由原 API 最终裁定。
7. Runtime 仅改变自己的状态：缺员工信息为 `needs_input`；等待前单、同事、事实、日期或原页面为 `waiting`；准备成功为 `awaiting_confirmation`；原回执/真实结果证明必要步骤完成才为 `completed`。`uncertain` 阻塞依赖，查不到回执不重放 POST。原单读权限变化为 waiting/权限失效，不暴露旧快照。
8. 现有 Proposal 是唯一确认对象。adapter 只声明可准备的原 operation/schema/ref，不直接执行；稳定 WorkItem 及批量行 ID 由核心运行时提供；同一原意图在重启/重复唤醒后只关联同一张卡。不能把模型工具数、成卡数或无待办作为验收成绩。
9. 每项只允许新增/修改 `app/assistant_runtime_domains/<adapter>.py`、`app/assistant_runtime_domains/__init__.py` 中显式注册项和该项外部测试。注册项为确定映射，不动态导入模型提供的模块。现有 API、service、models、迁移、权限表、业务公式、原状态机默认只读。
10. 信号默认复用已经接好的原 FlowEvent/Proposal/Grant WakeEvent 与五分钟只读补漏。非 Case 对象确需即时信号时，只允许在本项列出的原 service 已有成功事实事务处增加一次已有 `emit_wake_event(db,...)` 调用：不增加 commit、不改顺序、不调模型。先记录准确 hook 位置及回滚证明，再实施；不能把“等待即时通知”扩大为改写原领域。
11. WakeEvent 使用真实来源键和对象引用，实例为 `flow_event:<id>` 或已落库的领域事实事件 ID；PlanStep 的目标对象与其 `evidence_refs` 中确证的来源对象参与匹配。沿用 ARCHITECTURE 的 `Run.trigger_key` 保留 `signal_key`/事件来源引用并参与已有唯一键，不为 Run 新增 `wake_event_id` 列或另一套事件关联字段。RunItem 关联稳定 WorkItem，成功卡用 source_work_item_id 唯一关联；不得按标题或自由文本连接事件。快照只读缺少事件时补漏查询，不拿时间戳拼业务成功事件。
12. 统计没有原生单据 ID 时，`ref.type='report_query'`、`ref.id=本人既有 WorkItem.id`；该 WorkItem 的 `item_kind=read`、`validated_intent` 保存受评审 GET operation_id/path_args/query。adapter 从服务器校验后的参数恢复查询，不新增查询表。report snapshot 只能作查询结果，不能成为付款/库存完成事实；真实 DailyReport 则继续使用原 report_id。

回执映射中的 operation_id 指该笔冻结提交的原操作；回执读取复用前置统一 resolver 的注册 handler，不要求每个领域新增 receipt GET。只有确实需要新增只读 API 且被前置里程碑明确授权时才使用该接口，本章不得为填映射表编造路由。

每项下列“注册合同”冻结有限 object_type/fact_key 及其原生主键来源；这些是对原实体的类型化引用，不新建业务实体/状态。注册位置固定为 `app/assistant_runtime_domains/__init__.py`。多个 adapter 服务同一 `case` 或 `group_member` 时，保留同一原引用；注册表依据服务器已证明的原 kind/flow_version、确定 operation_id 与带领域前缀的 fact_key 分派，不给同一键注册两个 provider，不新增 ref 字段或由模型决定模块。`report_query` 按本人 WorkItem.validated_intent 的确定 GET operation_id 分派；未知类型/键/操作均拒绝，不能动态导入或解释表达式。

事实读取必须先通过原授权 GET 或统一只读回执 resolver；下列模型名仅指明原证据来源，不允许 adapter 绕过授权直接扫描表。`satisfied=true` 必须有本对象/本版本的可读原证据；只有原授权读法完整且明确证明条件不成立才可为 false。字段缺失、分页未穷尽、读权限不足、无公开原事实、未知版本、原关联/回执无法定位以及不适用类型一律 `satisfied=null`（unknown）并给 reason，不能降为 false 自动补办。原动作成功证据只能来自已关联 WorkItem 的冻结提交及真实回执，不靠枚举请求号找记录；动作成功也不证明以后一直保持同一业务条件。

带 `*_recorded`/`*_linked`/`*_posted` 的存在键，除正文明确声明“全部”外，只证明至少一笔注明的原事实，并保留对应原行/方案/批次 evidence_refs。它不能独自作为“全部收齐/款齐/完工/退款完毕”的完成条件；需要确定某行或全量完成而现有原读取不能证明时报告 unknown/能力缺口。禁止事后给 fact_key 拼 ID/金额/任意过滤器；如需要新增键，先改规格和确定性夹具再单独评审。所有 report_query/只读系统项的 `fact_keys=[]`；查询完成只由 Run/WorkItem 表达，不生成业务完成事实。

### 每项必读的共同现有文件

`total_plan.md`、`app/business_assistant_business_tools.py`、`app/business_assistant_gateway.py`、`app/business_assistant_capabilities.json`、`app/business_assistant_workboard.py`、`app/business_assistant_service.py`、`app/tenancy.py`。实施时还必须读本轮已落地的 PROJECT_SPEC、ARCHITECTURE 和前置 runtime 接口，本文不替代它们。

### 外部验证命令和基础验收

M0 负责建立以下 runner 与 manifest；以下均为待实现的准确命令，不代表已运行。runner 每次从 `--repo` 生成无敏感数据的当前源码镜像，再用独立合成数据库执行，不得加载归档旧业务代码或原预览配置。

```powershell
$RepoRoot = (Resolve-Path '.').Path
$ValidationRoot = 'C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'
$ValidationPython = "$ValidationRoot/.venv/Scripts/python.exe"
```

每个小项的 suite 必须包含：允许/拒绝岗位与门店一致、未知 ID/版本、真实对象及结果类型、正常准备后人工原确认、重复 WakeEvent/WorkItem 不重复成卡、原事实变化、未开启 Grant 不自动准备、未知结果不重放。只读项不强造写入/回执用例，而应验证查询不产生 Proposal/业务行。业务写入测试只能由合成员工测试客户端点击原确认；模型和 worker 自身不能提交。

涉及小 signal hook 时，补充“原业务回滚则 WakeEvent 同时回滚；重复事件不重复通知/成卡”；无需新增 hook 的项记录“复用既有 signal/补漏”，不改原业务文件。以下每项都还应通过其原业务族适用回归；恢复的原测试名由 M0 manifest 从归档实际发现后登记，不能编造已存在的旧测试命令。

### 当前已查证的动作可用性缺口

下列原详情里的字符串 actions 主要表示岗位可见。它们不证明该动作此时可执行，也不能直接满足 `native_action_available`。实施该小项时须记录目前能由原授权 GET/既有纯只读 guard 证明的范围；若下述条件仍不能得到只读证明，对应自动续办链必须以缺口列入验收结果，不能将“可以准备一张卡”写成“已经完全闭环”。可证明的独立事实条件仍可正常唤醒；不能在 adapter 重写业务状态机、试调 command 或通过一组手抄判断冒充原守卫。

| 受影响小项 | 已查证的展示与真实守卫 | 必须明确报告的自动续办缺口 |
| --- | --- | --- |
| M7.5.1 物资采购 | `app/procurement_service.py:98` 的 actions 仅筛岗位；`:255-268` 实收还要求采购批准且未关闭、真实收货待办、证据、各行归属与剩余数量。 | `receive` 出现在列表不能证明到货即可自动进入可确认实收。没有覆盖这些前提的原只读证明时 availability 必须 unknown，等待原页面/员工补充实收与证据；不能以发运或付款替代到货。 |
| M7.2.1 整车采购 | `app/vehicle_procurement_service.py:99` 仅筛岗位；`:274-278` 付款核对有效请款与双重余额；`:295-303` 验车核对在途发运、退回冲突、现场 VIN、仓库类别与保管身份。 | `pay`/`receive` 可见不证明款项可付或实车可入库。只读摘要不足以证明特定请款/发运/库位全部前提时，不承诺付款到验车的自动续办闭环；实际资金、现场 VIN 和实物交接仍须人工事实。 |
| M7.3.2 维修 | `app/repair_service.py:481` 仅筛岗位；`:426-435` 完工/质检核对授权、开工与配件领齐；`:454-459` 交车另验冻结结算、本人待办、证据、套餐 guard、权益占额与客户欠款。 | `finish`/`quality`/`release` 可见不证明可继续该步骤。配件、套餐及多方结算跨域前提缺少原只读证明时，不能声称维修完成后一定自动准备可确认交车；已证明的付款或领料事实仅可触发重新查询。 |
| M7.12.1 保险 | `app/insurance_service.py:338` 只按岗位与非 cancelled 显示；`:268-283` 原授权/提交核对当前已批且未过期报价摘要、原任务、证据、撤保/已出保状态、上次提交真实结果。 | 报价通过、收款或 actions 含 `submit` 不等于可以再次投保。旧提交无结果、报价过期/撤保中等前提无只读证明时等待员工；不能伪造保险公司结果或承诺自动承保闭环。 |
| M7.12.2 加装 | `app/addon_service.py:581` 只按岗位与非 cancelled 显示；`:439-447` 授权涉及当前审批及库存可领与占用；`:452-466` 安装、复检、接收核对原批次、未结束处置、整改和全部实际履约。 | `authorize`/`quality`/`accept` 可见不证明可占用库存、可复检或可接收。库存与处置条件无法由原只读证明时 availability=unknown，不能以准备卡或质检任务关闭宣称整单可交付。 |
| M7.12.3 代办服务 | `app/service_orders_service.py:480` 只按岗位与非 cancelled 显示；`:383-401` 原办理核对当前授权、终止方案、原项目、最新提交/补件结果、实际批准及第三方净支付。 | `submit`/`fulfill` 可见不证明外部手续可继续或已办结。缺少真实外部结果或特定项目支付证明时必须等待；不能把模型摘要或无待办当作可办结事实。 |

与上述情形区分：`app/flow_engine.py:495-513` 的原通用动作读法确实计算 state/role、blocker 与来源限制并返回 enabled/reason；只有该原读法实际适用的对象与动作可沿用这个证明，不能拿它替代专用 service 的守卫。每项验收记录须列出支持的条件、返回 unknown 的条件及因此未闭环的场景；没有只读证明的 gap 保持公开，不在本章默认获准改写原 API。

## M7.1 销售接待、报价与售后

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-1-1"></a>

### M7.1.1 售前接待与意向跟进

**状态**：implemented（2026-09-28 实现并完成外部实测；10 项通过）

**全局顺序前置**：M6.8 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/lead.py`（`LeadAdapter(FlowCaseAdapter)`，`kind='lead'`、`flow_version=1`：`read_snapshot` 单次受控 GET 且只接受 lead、`extract_result` 只对登记 operation、`read_receipt` 复用父类回执族；三条登记事实 `lead.customer_linked`/`lead.owner_assigned`/`lead.reserve_recorded` 均有原详情直接证据，无证据时 `satisfied=None` 或 `False` 并给出原页面入口），并在 `app/assistant_runtime_domains/__init__.py` 显式注册（`operation_ids=(GET /api/flow/cases/{case_id}, POST /api/flow/cases, POST /api/flow/cases/{case_id}/actions/{action})`、`kind_versions=fact_kind_versions=(('case','lead',1),)`、`fallback_object_types=()`），未改原业务文件、迁移、权限或状态机，未新增 signal hook。实测发现并修复：`read_snapshot` 未按 kind 收口、reserve 事实读错原生 payload 层级、回执夹具缺少冻结提交标识。外部套件 `$ValidationRoot/tests/runtime_domains/test_lead.py`（10 项），run `20260928T125128Z-3f52688e9d` passed；同指纹 M1.4、M0.1 与 M0.2.B 三项助手检查全部通过。详见 `docs/implementation-checkpoints/M7-1-1-review-v1.md`。源码指纹 `c04dde7ea3ec10d8c915e9e0c2e922a6ec919fb68fc9780b3e7476b3f70cd36b`。下一项 M7.1.2。



**目标**：只完成 `lead` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/flow_specs.py`、`app/flow_api.py`、`app/flow_engine.py`。

**允许改**：新文件 `app/assistant_runtime_domains/lead.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_lead.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/flow/cases/{case_id}；flow_specs.py:48-54 的 assign、intent、remind、follow、reserve、close、reopen；按原 flow_version 取动作。

**注册合同**：object_type=case（原 Case.id；kind/flow_version 依原 lead 定义）；adapter=`app/assistant_runtime_domains/lead.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`lead.customer_linked`：原详情 customer_id 指向本店可读客户；`lead.owner_assigned`：原详情 owner_id 为原实际负责人；`lead.reserve_recorded`：原 reserve 成功结果/原事件确证本 lead 派生的车辆订单 ID，不能以 follow 待办结束代替。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原 contact/follow 任务、实际 owner/customer 引用与 due_date；只在真实 reserve 结果中提取车辆订单引用。
3. 接统一只读回执 resolver：flow_request_receipts，复用 flow.request_digest/prior_request 规则。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：同名客户不默选；closed/reopen 以原动作可用性为准；客户不希望联系时不得继续生成联系任务。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_lead.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.1.1
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-1-2"></a>

### M7.1.2 版本报价与车辆交付

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.1.1 done。

**验证状态**：映射/快照/三条事实/报价族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/sales_order.py`（`SalesOrderAdapter(FlowCaseAdapter)`，`kind='order'`、`flow_version=3`：`read_snapshot` 单次只读 `GET /api/sales-quotes/orders/{key}` 且收口 kind、`extract_result` 覆盖报价族 operation、`read_receipt` 走报价族回执并保持冻结 `request_id`；事实 `sales.active_quote_approved`/`sales.active_quote_consented`/`sales.delivery_recorded` 分别以原 review 决定与 resolution、`sales_consent_id`+`signed_file`、原交付事实键为准，缺证据即未知，报价批准不等于交付），并在 `__init__.py` 显式注册（`kind_versions=fact_kind_versions=(('case','order',3),)`、`fallback_object_types=()`）。实测发现并修复：跨店读取误判 502（改为 404 且不暴露旧快照）、快照要求原待办携带真实 `case_id`、未绑定回执族的夹具写错。外部套件 `$ValidationRoot/tests/runtime_domains/test_sales_order.py`（9 项），run `20260928T130043Z-76ef912e42` passed；同指纹 M7.1.1 仍通过。详见 `docs/implementation-checkpoints/M7-1-2-review-v1.md`。源码指纹 `e04c4efb5d90ceb5d22b98572e30bb053c91dbed1f2735aec6bed61e87bcfe40`。下一项 M7.1.3。



**目标**：只完成 `sales_order` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/sales_quote_api.py`、`app/sales_quote_service.py`、`app/sales_quote_specs.py`、`app/sales_quote_finance.py`、`app/flow_api.py`。

**允许改**：新文件 `app/assistant_runtime_domains/sales_order.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_sales_order.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/sales-quotes/orders/{key} 和 GET /api/flow/cases/{case_id}；sales_quote_specs.py:11-15 的 quote_approve/quote_reject/quote_withdraw/release_vehicle/refund_excess；原 allocate/sign/receive/inspect/dispatch/deliver 仍由当前版本返回。

**注册合同**：object_type=case（原销售 Case.id；原报价版本为子事实）；adapter=`app/assistant_runtime_domains/sales_order.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`sales.active_quote_approved`：原 active_quote_id 指向的 SalesQuoteReview.decision=approved，且其原 resolution 未撤回；`sales.active_quote_consented`：原 sales_consent_id 的 SalesQuoteConsent 明确关联 active_quote_id、实际车辆与签回证据；`sales.delivery_recorded`：原 deliver 成功回执及重读原交付事实吻合，不能以 dispatch 或金额结清替代。pending_quote_id 的新报价不得借用 active 旧版事实自动推进。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：当前批准报价、客户同意版本、实配车辆、原收退款、真实签回/检查/出库/交付引用分别作为事实；不得把报价批准当交付。
3. 接统一只读回执 resolver：flow_request_receipts；sales_quote_service._execute 的 operation/payload 摘要，不能套通用 flow action 摘要。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：新报价使旧依赖过时；车辆被另一订单占用、超收退款未办、检查不通过分别保持 waiting/needs_input；未知收款进入 uncertain。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_sales_order.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.1.2
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-1-3"></a>

### M7.1.3 退订退车及维修退款纠正

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.1.2 done。

**验证状态**：映射/快照/三条事实/售后族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/aftercare.py`（`AftercareAdapter(FlowCaseAdapter)`，`kind='aftercare'`、`flow_version=2`：`read_snapshot` 单次只读 `GET /api/aftercare/orders/{case_id}` 并收口 kind/scenario、`extract_result` 覆盖售后族 operation、`read_receipt` 走 `AftercareReceipt` 族并保持冻结 `request_id`；事实 `aftercare.plan_applied`（须原 `applied=true` 且有方案编号）、`aftercare.customer_consent_recorded`（须原同意记录）、`aftercare.cash_refund_recorded`（须本单原 `AftercareCashRefund` 引用；批准/生效/集团退回都不满足）），并在 `__init__.py` 显式注册（`kind_versions=fact_kind_versions=(('case','aftercare',2),)`、`fallback_object_types=()`）。外部套件 `$ValidationRoot/tests/runtime_domains/test_aftercare.py`（9 项），run `20260928T130312Z-302fe6b28e` passed；同指纹 M7.1.1、M7.1.2 回归通过。详见 `docs/implementation-checkpoints/M7-1-3-review-v1.md`。源码指纹 `cb48b2d9ef1b2f87300685e47981b5ae227ad02f4404e5a1f9f8a09af3089c87`。下一项 M7.2.1。



**目标**：只完成 `aftercare` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/aftercare_api.py`、`app/aftercare_service.py`、`app/aftercare_models.py`、`app/group_aftercare.py`。

**允许改**：新文件 `app/assistant_runtime_domains/aftercare.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_aftercare.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/aftercare/orders/{case_id}；原 scenario=sale_termination/vehicle_return/repair_refund；service.command 中 execution/plan/approve/customer_confirm/apply/refund。

**注册合同**：object_type=case（AftercareOrder.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/aftercare.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`aftercare.plan_applied`：当前方案有原 AftercareApplication；`aftercare.cash_refund_recorded`：本单原 AftercareCashRefund 及关联现金来源存在；`aftercare.customer_consent_recorded`：当前方案有原 AftercareConsent。批准或生效不满足实际退款键。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原 source_case、独立方案/批准/客户确认、退款来源及实物处理引用；分清方案生效与实际退款。
3. 接统一只读回执 resolver：aftercare_receipts/AftercareReceipt，沿 aftercare_service._execute 摘要。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：已开展的加装保险代办需要独立处置；前序取消不能完成后续；未知退款不重放；集团本金和权益退回不冒充现金。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_aftercare.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.1.3
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

## M7.2 整车采购、仓库与批量来源

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-2-1"></a>

### M7.2.1 整车采购逐 VIN 进度

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.1.3 done。

**验证状态**：映射/快照/三条事实/采购族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/vehicle_purchase.py`（`VehiclePurchaseAdapter(FlowCaseAdapter)`，`kind='vehicle_procurement'`、`flow_version=2`：`read_snapshot` 单次只读 `GET /api/vehicle-procurement/orders/{case_id}`，旧/未知版本 404 兜底、跨店与原岗位 403 都不暴露旧快照；`extract_result` 覆盖采购族 operation；`read_receipt` 走 `vehicle_purchase_` 前缀回执族并保持冻结 `request_id`；事实 `vehicle_purchase.shipment_recorded`（原 Shipment）、`vehicle_purchase.receipt_recorded`（原 Receipt 且带 shipment/vehicle 引用，逐 VIN）、`vehicle_purchase.payment_recorded`（`direction='out'` 的原 Payment；付款申请不满足，岗位不可见时未知）——三个键都只证明至少一笔，不声明整批齐套），并在 `__init__.py` 显式注册（`kind_versions=fact_kind_versions=(('case','vehicle_procurement',2),)`、`fallback_object_types=()`）。外部套件 `$ValidationRoot/tests/runtime_domains/test_vehicle_purchase.py`（9 项），run `20260928T130552Z-33d5660f42` passed；同指纹 M7.1.3 回归通过。详见 `docs/implementation-checkpoints/M7-2-1-review-v1.md`。源码指纹 `936951adca48b39bbfecb6af8306eef828c17cb8b169e7cdec1dc44bdaf5bcd9`。下一项 M7.2.2。



**目标**：只完成 `vehicle_purchase` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/vehicle_procurement_api.py`、`app/vehicle_procurement_service.py`、`app/vehicle_procurement_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/vehicle_purchase.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_vehicle_purchase.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/vehicle-procurement/orders/{case_id}；service.py:26-32 的 approve/request_funds/pay/ship/receive/return_request/return_approve/return_dispatch/refund。

**注册合同**：object_type=case（VehiclePurchaseOrder.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/vehicle_purchase.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`vehicle_purchase.shipment_recorded`：本单存在原 VehiclePurchaseShipment；`vehicle_purchase.receipt_recorded`：本单存在原 VehiclePurchaseReceipt 及其 shipment/VIN/vehicle 引用；`vehicle_purchase.payment_recorded`：本单存在 direction=out 的原 VehiclePurchasePayment。三个键只证明至少一笔对应事实，不能声明整批齐套。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：逐 VIN 的 Shipment、VehiclePurchaseReceipt、付款申请和实际付款/退款；在途、验收入库、付款分别保持事实。
3. 接统一只读回执 resolver：flow_request_receipts；vehicle_procurement_service.execute 使用 vehicle_purchase_ 前缀；VehiclePurchaseReceipt 仅是实物事实。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：同 VIN 重复/价格版本变化/未发运余量取消；一批部分验收逐行展示，不以一张总卡成功表示所有车辆入库。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_vehicle_purchase.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.2.1
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-2-2"></a>

### M7.2.2 整车库位及出退库作业

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.2.1 done。

**验证状态**：映射/快照/三条事实/作业族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/vehicle_operation.py`（`VehicleOperationAdapter(FlowCaseAdapter)`，`kind='vehicle_operations'`、`flow_version=2`：`read_snapshot` 单次只读 `GET /api/vehicle-operations/orders/{case_id}`，kind 收口 422、缺来源车辆 502（不补默认值）、原岗位拒绝与原单不可见都不暴露旧快照；`extract_result` 覆盖作业族 operation；`read_receipt` 走 `vehicle_operation_` 前缀回执族并保持冻结 `request_id`；事实 `vehicle_operation.dispatch_recorded`（本单原位置流水负数 `inventory_delta`）、`vehicle_operation.accept_recorded`（正数 `inventory_delta`）、`vehicle_operation.inspection_recorded`（原 `VehicleReturnInspection` 存在；**只证明已登记检查，不等于合格**）），五类业务类别与原 `KINDS` 表一致，并在 `__init__.py` 显式注册（`kind_versions=fact_kind_versions=(('case','vehicle_operations',2),)`、`fallback_object_types=()`）。首轮套件仅 8 项低于登记的 9 项下限被运行器如实拦截，已补映射保真断言后复跑通过。外部套件 `$ValidationRoot/tests/runtime_domains/test_vehicle_operation.py`（9 项），run `20260928T130920Z-3f226e165b` passed；同指纹 M7.2.1 回归通过。详见 `docs/implementation-checkpoints/M7-2-2-review-v1.md`。源码指纹 `f518dd66a12d17283230564336fe2d0044c7e1ab60688ad228e47f7073afbc2f`。下一项 M7.2.3。



**目标**：只完成 `vehicle_operation` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/vehicle_operations_api.py`、`app/vehicle_operations_service.py`、`app/vehicle_operations_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/vehicle_operation.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_vehicle_operation.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/vehicle-operations/orders/{case_id}；原 kind=locate/local_move/other_out/other_return；LABELS 的 approve/locate/dispatch/accept/inspect/disposition。

**注册合同**：object_type=case（VehicleOperation.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/vehicle_operation.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`vehicle_operation.dispatch_recorded`：原 dispatch 成功结果及本单 VehiclePositionEntry 确证实际发出；`vehicle_operation.accept_recorded`：原 accept 成功结果及本单接收位置流水；`vehicle_operation.inspection_recorded`：本单原 VehicleReturnInspection 存在，不能将检查存在解释为合格。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原库位、在途与实际接收、实车检查及处置决定；读取原任务承担岗位。
3. 接统一只读回执 resolver：flow_request_receipts；vehicle_operation_ 摘要族。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：拒收、整改、退回客户按原动作等待；未知库位/车辆不可配不补默认值；禁止改 Vehicle.store_id。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_vehicle_operation.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.2.2
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-2-3"></a>

### M7.2.3 整车批量导入后的审阅与逐行恢复

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.2.2 done。

**验证状态**：目录规则、快照、三条事实、回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/vehicle_import_batch.py`（`VehicleImportBatchAdapter`，`object_types=('vehicle_import_batch',)`：快照只读 `GET /api/vehicle-imports/batches/{batch_id}`（**实测 `business_assistant_gateway._operations()`：写操作须在 reviewed catalog 内，GET 由活跃路由发现并受 domain/closed/denied/body 过滤与调用时授权**），动作走已评审 `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}`；事实 `vehicle_import.reviewed`/`vehicle_import.confirmed` 按原 `status`（已审阅不等于已确认），`vehicle_import.all_rows_result_recorded` 要求 `len(rows)==row_count` 且每行按 kind 有真实 `funds_request_id`/`shipment_id`/`receipt_id`，缺行、重复行标识、未登记类别、缺结果字段一律 unknown；回执走 `VehicleImportRequest` 族并保持冻结 `request_id`），`__init__.py` 显式注册且 `fallback_object_types=()`。**实测发现并修复**：① 我先前误把 JSON 目录当作读取白名单、错报"能力缺口"，实测原网关目录规则后撤回（撤回说明见 `docs/implementation-checkpoints/M7-2-3-capability-gap.md`）；② 批次对象不是 Case，父类 `snapshot_from_record` 按 `case` 校验引用导致 422，改为直接投影统一快照 DTO，动作可用性一律 `unknown`；③ 首轮 8 项低于登记下限被运行器如实拦截，现为 9 项。外部套件 `$ValidationRoot/tests/runtime_domains/test_vehicle_import_batch.py`（9 项），run `20260928T131640Z-e250f94ef3` passed；同指纹 M7.2.2、M7.2.1 回归通过。详见 `docs/implementation-checkpoints/M7-2-3-review-v2.md`。源码指纹 `46229e32526130166d92e4ba72828d3053f0c33f8c3774206c9bc7adc7ef9bcd`。**遗留**：文件上传仍是原封闭面；批次动作的准备/确认链路属集中测试阶段。下一项 M7.3.1。

### M7.3.1 维修预约与实际到店接待

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.2.3 done。

**验证状态**：映射/快照/三条事实/预约族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/service_intake.py`（`ServiceIntakeAdapter`，`object_types=('service_appointment',)`：快照单次只读 `GET /api/service-intake/appointments/{key}` 且不补默认车辆、`extract_result` 覆盖预约族三条 operation、`read_receipt` 走 `IntakeReceipt` 族并保持冻结 `request_id`；事实 `intake.arrival_recorded`（必须原 `ArrivalFact` 确证到店时间，**资源占用不等于实际到店**）、`intake.repair_converted`（必须与原维修单引用吻合）、`intake.cancelled`（重读状态为 `cancelled`，**`no_show` 不等于取消**）；原详情不返回动作可用性，故六个动作一律 `unknown`，由原 API 最终裁定），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未占用资源、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_service_intake.py`（9 项），run `20260928T131920Z-f1898bd604` passed；同指纹 M7.2.3 回归通过。详见 `docs/implementation-checkpoints/M7-3-1-review-v1.md`。源码指纹 `2df2c8248fa906d35ccfc1ee7a7a2f4540dc2aca37ba1f89ca07895d4e79bb1e`。下一项 M7.3.2。

### M7.3.2 维修工单接车与施工进度

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.3.1 done。

**验证状态**：映射/快照/三条事实/维修族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/repair_order.py`（`RepairOrderAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/repair-orders/{case_id}`，动作只保留原返回的岗位筛选名字且可用性一律 `unknown`；`extract_result` 覆盖维修族三条 operation；`read_receipt` 走 `repair_v3_` 前缀回执族并保持冻结 `request_id`；事实 `repair.current_quote_authorized`（当前报价=未取消版本中 revision 最大者，须有原授权事实，**已取消的高版本不得顶替**）、`repair.passed_quality_recorded`（必须当前报价对应的原 `RepairQuality.passed=true`，旧报价质检不算）、`repair.release_recorded`（必须原 `data.released_date` 与 `release_evidence_id` 同时存在；质检通过或收款完成都不能替代实际交车，字段不可见时返回未知）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。**实测发现并修复**：① 首轮 8 项低于登记下限被运行器如实拦截，补上"注册真的到达运行时注册表"的接线断言后为 9 项；② 该接线断言先后缺 `REPAIR_FACTS`/`REPAIR_READ` 导入（真实 NameError），补齐后通过。外部套件 `$ValidationRoot/tests/runtime_domains/test_repair_order.py`（9 项），run `20260928T132339Z-95f7d86681` passed；同指纹 M7.3.1 回归通过。详见 `docs/implementation-checkpoints/M7-3-2-review-v1.md`。源码指纹 `eda2ac9fb122bffad9d548579402e5deb24e8810afeb2b0092677893c7ed2137`。下一项 M7.3.3。

### M7.3.3 维修领退料与返修

**状态**：implemented（2026-09-28 实现并完成外部实测；10 项通过）

**全局顺序前置**：M7.3.2 done。

**验证状态**：映射/快照/三条事实/授权族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/rework_grant.py`（`ReworkGrantAdapter`，`object_types=('rework_source_grant',)`：快照单次只读 `GET /api/rework-extensions/grants/{key}`，动作只保留原返回名字且可用性一律 `unknown`，跨店授权按原详情透传（不补默认门店、不改 `store_id`）；`extract_result` 覆盖授权族五条 operation；`read_receipt` 走 `ReworkGrantReceipt` 族（派生接待命令仍按 `IntakeReceipt`，不在本适配器范围）；事实 `rework.approval_recorded`（只有经 approve 决定才离开 pending/rejected，且明确"批准历史不证明当前未撤销或仍有可用范围"）、`rework.revocation_recorded`（状态确为 `revoked`）、`rework.extension_recorded`（**该详情不提供 ReworkExtension 承接关系，一律返回未知**，绝不用批准历史代替）；责任授权额度只投影原 `original_liability_limit_cents`，客户自费部分不推断），`__init__.py` 显式注册且 `fallback_object_types=()`。外部套件 `$ValidationRoot/tests/runtime_domains/test_rework_grant.py`（10 项），run `20260928T132534Z-b69cd96f4f` passed；同指纹 M7.3.2 回归通过。详见 `docs/implementation-checkpoints/M7-3-3-review-v1.md`。源码指纹 `71ecab9e9cce1353da696460c6d02e7968412fce159cbc9182d082c6026f6156`。下一项 M7.3.4。

### M7.3.4 理赔核赔受理

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.3.3 done。

**验证状态**：映射/快照/三条事实/理赔族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/claim_order.py`（`ClaimOrderAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/claims/{case_id}`，动作只保留原返回名字且可用性一律 `unknown`，缺原维修来源 502（不补默认值）；`extract_result` 覆盖理赔族三条写/读 operation；`read_receipt` 走 `ClaimReceipt` 族（`request_digest('claims_'+operation, payload)`）并保持冻结 `request_id`；事实 `claim.transmission_recorded`（本单原 `ClaimTransmission`）、`claim.external_result_recorded`（本单原 `ClaimResult`，**保留原 outcome 且明确"结果本身不代表已批准或已收款"**）、`claim.binding_recorded`（本单原 `ClaimBinding` 必须指明 `payment_route`，缺去向返回未知；**核赔或绑定不代表现金已收**）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。**实测发现并修复**：派生登记脚本的 `minimum_tests` 未随本项套件规模（8 项）更新，首轮被 `below_registered_minimum` 如实拦截；按实际规模对齐后通过（未虚增断言）。外部套件 `$ValidationRoot/tests/runtime_domains/test_claim_order.py`（8 项），run `20260928T132759Z-33150cb5d2` passed。详见 `docs/implementation-checkpoints/M7-3-4-review-v1.md`。源码指纹 `d5c4f445b1d001fdb398cfb01d9b32566d245f3b4069abe0c9e8492031ac843a`。下一项 M7.3.5。

### M7.3.5 维修出厂与真实进出厂时间

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.3.4 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/gate_visit.py`（`GateVisitAdapter`，`object_types=('gate_visit',)`：快照单次只读 `GET /api/gate-visits/{key}`，缺车辆引用 502（不补默认值），动作只保留原返回名字且可用性一律 `unknown`；`extract_result` 覆盖进出厂族六条 operation（含纠正与出厂动作）；`read_receipt` 由已评审的 flow receipt resolver 绑定并保持冻结 `request_id`；事实 `gate.arrival_recorded`（原 `arrive` 确证的 `arrived_at`，**计划日期不满足**，`voided` 即视为被纠正作废）、`gate.departure_recorded`（原 `leave` 确证的 `left_at`，取消或计划都不满足）、`gate.handoff_recorded`（原 `GateHandoff` 引用的实际维修接待）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_gate_visit.py`（8 项），run `20260928T132917Z-2ce68f4fa8` passed；同指纹 M7.3.4 回归通过。详见 `docs/implementation-checkpoints/M7-3-5-review-v1.md`。源码指纹 `2b6f7a3af2fe7599c860745a9e867079395069d847a073527618c1414c7a3ab3`。下一项 M7.4.1。

## M7.4 精品物资销售与混合支付

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-4-1"></a>

### M7.4.1 精品销售与套餐

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.3.5 done。

**验证状态**：映射/快照/三条事实/精品族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/retail_order.py`（`RetailOrderAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/retail/orders/{key}`，跨店/ID 不一致 502（不补默认门店），动作可用性一律 `unknown`；`extract_result` 覆盖精品族三条 operation；`read_receipt` 走 `retail_` 前缀回执族并保持冻结 `request_id`；事实 `retail.dispatch_recorded`（本单原 `RetailDispatch` 且带原行引用，**明确"至少一行、整单是否出齐以原单逐行为准"**）、`retail.accept_recorded`（必须原单实际接收事实；该详情未提供或岗位不可见时返回未知，不猜）、`retail.return_posted`（必须原 `RetailReturnPosting` 确证的退回数量 `returned_milli>0`）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_retail_order.py`（9 项），run `20260928T133123Z-01de12d08c` passed；同指纹 M7.3.5 回归通过。详见 `docs/implementation-checkpoints/M7-4-1-review-v1.md`。源码指纹 `d15f568c5517a70997600159af85d13e660f6293f4110b1b727e32e64e171b31`。下一项 M7.4.2。

### M7.4.2 精品套餐核销与安装

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.4.1 done。

**验证状态**：规则快照/两条事实/回执合同在隔离夹具中通过；销售侧无已评审读取路径，按合同返回未知。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/retail_bundle.py`（`RetailBundleAdapter`，`object_types=('retail_bundle_rule', 'retail_bundle_sale')`：规则快照单次只读 `GET /api/retail-bundles/rules/{key}/preview`（`sets=1` 只读求值），冻结组件缺失即 502；事实 `retail_bundle.rule_snapshot_readable`（真实规则 + 冻结组件/分摊完整）只用于规则；`retail_bundle.sale_linked` 需要原套餐销售详情核对派生 retail Case，而**该读取路径既未在 reviewed catalog 也未被活跃路由发现**（只有 `POST /api/retail-bundles/sales`），故销售对象**不编造读取路径**：`read_snapshot` 返回 503 并给原页面入口（套件断言零读取），事实返回未知；`extract_result` 对销售绑定其**派生 retail Case**、对规则返回规则引用；`read_receipt` 走规则版本族摘要并保持冻结 `request_id`），`__init__.py` 显式注册且 `fallback_object_types=()`。实测修正：套件把"不适用对象类型"误当形状错误（与合同"不适用类型返回 unknown"冲突），按合同修正断言，产品代码未放宽带宽。外部套件 `$ValidationRoot/tests/runtime_domains/test_retail_bundle.py`（9 项），run `20260928T133417Z-862fad401d` passed。详见 `docs/implementation-checkpoints/M7-4-2-review-v1.md`。源码指纹 `a94a84a4d03cf866c6f11abbe89bc001c2285629679a32571f4ed3438197c107`。**遗留**：销售侧核销/安装事实需评审补一条销售详情只读路径后方可验证。下一项 M7.4.3。

### M7.4.3 零售集团与门店规则

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.4.2 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/retail_group_payment.py`（`RetailGroupPaymentAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/retail-group/orders/{case_id}`，ID 不一致或缺原集团方案 502（不补默认值），动作可用性一律 `unknown`；`extract_result` 覆盖集团支付族动作 operation（只读目录不属结果 operation）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `retail_group.reservation_recorded`（原 `RetailGroupReservation`，tender 带 `reservation_version`）、`retail_group.capture_recorded`（原 `RetailGroupCapture`，tender 状态 `captured`）、`retail_group.restore_recorded`（原 `RetailGroupRestore`，按原恢复读法状态 `released`）——**分别只证明实际一笔占用/核销/恢复，不证明整单现金到账**；明细岗位不可见时一律未知），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_retail_group_payment.py`（7 项），run `20260928T133541Z-d2be66e157` passed；同指纹 M7.4.2 回归通过。详见 `docs/implementation-checkpoints/M7-4-3-review-v1.md`。源码指纹 `2b209aa9974d7cf309647e1f5f3573c3a5846f70f27ff0dc205bf340db442499`。下一项 M7.5.1。

## M7.5 物资采购与仓储

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-5-1"></a>

### M7.5.1 物资采购、预付与仓储

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.4.3 done。

**验证状态**：映射/快照/三条事实/采购族回执在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/material_procurement.py`（`MaterialProcurementAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/procurement/orders/{case_id}`，跨店/ID 不一致 502，动作可用性一律 `unknown`；`extract_result` 覆盖采购族三条 operation；`read_receipt` 走 `procurement_` 前缀回执族并保持冻结 `request_id`；事实 `procurement.receipt_recorded`（必须原 `PurchaseReceipt` **且**原 `StockMove`；**关闭收货余量不满足实收键**，一笔不等于全部行完成）、`procurement.return_posted`（原退货过账且指向原收货批次；引用形状未登记即未知）、`procurement.payment_recorded`（原 `PurchasePayment` 且带实际付款来源；收货或应付不满足，金额岗位不可见时未知）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_material_procurement.py`（8 项），run `20260928T133741Z-092a9feee6` passed；同指纹 M7.4.3 回归通过。详见 `docs/implementation-checkpoints/M7-5-1-review-v1.md`。源码指纹 `d04af44e4200d64bc3b474d9edf1bbda6b32ec3e65abe4b03f74f171ff507819`。下一项 M7.5.2。

### M7.5.2 物资采购预付

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.5.1 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/procurement_prepayment.py`（`ProcurementPrepaymentAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/procurement/orders/{case_id}`（原采购详情已挂预付款面，未启用门店即视为不完整），六个 `prepay_*` 动作仍挂原采购动作且可用性一律 `unknown`；`extract_result` 覆盖采购族 operation；`read_receipt` 继续沿采购 flow_req 族并保持冻结 `request_id`；事实 `prepayment.approval_recorded`（原 `PurchasePrepaymentDecision.action='approve'`，理由带申请 ID 且明确"批准不等于已实际付款"，拒绝不满足）、`prepayment.disbursement_recorded`（该申请 `paid_cents>0`，对应原 disbursement/allocations 指向真实 `payment_id`；只证明该申请一笔，不串到另一申请）、`prepayment.expiration_recorded`（必须有原 `expire` 决定/成功结果；**仅 `valid_until` 过期不制造已过账事实**）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_procurement_prepayment.py`（7 项），run `20260928T133942Z-36bb9fca5b` passed。详见 `docs/implementation-checkpoints/M7-5-2-review-v1.md`。源码指纹 `febd9b70876c3648f3d32ef106987d25fc9bcd5ff9d535bafcff1354025c2749`。下一项 M7.5.3。

### M7.5.3 仓储单据

**状态**：implemented（2026-09-28 实现并完成外部实测；7 项通过）

**全局顺序前置**：M7.5.2 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/warehouse_document.py`（`WarehouseDocumentAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/warehouse/cases/{case_id}`，ID 不一致或未登记 operation 一律 502（不补默认值），动作可用性一律 `unknown`；`extract_result` 覆盖仓储族 operation；`read_receipt` 沿原 `digest(action, values)` 摘要族并保持冻结 `request_id`；事实 `warehouse.entry_recorded`（原详情流水至少一笔；未提供即未知）、`warehouse.count_observed`（原 `WarehouseCountObservation`，明确"实盘观察不等于已过账"）、`warehouse.count_posted`（必须原 post_count 回执**且**实际盘差 StockMove；实盘观察/批准/准备分配都不满足，未提供标记即未知，无差异明确未满足）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_warehouse_document.py`（7 项），run `20260928T134114Z-d3d89577cf` passed。详见 `docs/implementation-checkpoints/M7-5-3-review-v1.md`。源码指纹 `024186c59cb2bc9972b26fd01218ea60e1dc07523de0fe670a695f329a260441`。**遗留**：盘差过账与出入库流的判定需评审补只读标记。下一项 M7.6.1。

## M7.6 客户档案、服务、提醒与问卷

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-6-1"></a>

### M7.6.1 客户档案与服务单

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.5.3 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/customer_vehicle.py`（`CustomerVehicleAdapter`，`object_types=('customer_vehicle',)`：快照单次只读 `GET /api/customer-service/vehicles/{vehicle_id}`，历史关联只读同族 `.../history`，ID 不一致 502，动作可用性一律 `unknown`；`extract_result` 覆盖车辆/观察/关联族 operation（历史读不属结果 operation）；`read_receipt` 沿客户服务族回执并保持冻结 `request_id`；事实 `customer_vehicle.customer_linked`（原 `customer_id` 为正整数且详情带客户资料）、`customer_vehicle.observation_recorded`（必须原 `VehicleObservation` 且保留类型/日期/来源；**详情未提供观察清单即未知**）、`customer_vehicle.history_link_recorded`（原 `ServiceHistoryLink` 与该车辆一致；**历史关联不证明仍能读取关联原单正文**）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原观察纠正规则。外部套件 `$ValidationRoot/tests/runtime_domains/test_customer_vehicle.py`（9 项），run `20260928T134244Z-c02e2075c7` passed。详见 `docs/implementation-checkpoints/M7-6-1-review-v1.md`。源码指纹 `589f175fc1df52a3ce06f3a7c230361097801a3ce4cfae8d05d065e6fc83c176`。**遗留**：观察读取需评审补只读路径。下一项 M7.6.2。

### M7.6.2 客户关怀服务单

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.6.1 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/customer_care.py`（`CustomerCareAdapter`，`object_types=('care_case',)`：快照单次只读 `GET /api/customer-service/cases/{case_id}`，ID 不一致或未登记 subtype 一律 502，动作可用性一律 `unknown`；`extract_result` 覆盖关怀族 operation（创建响应取 `case` 键）；`read_receipt` 走 `CareReceipt` 族并保持冻结 `request_id`；事实 `care.followup_recorded`（原 `CareRecord` 可识别为 followup；**联系不到/拒绝联系保留原 contact_result，不冒充成功联系**）、`care.handoff_recorded`（原 handoff 记录**且**有可读负责人）、`care.closed`（原状态确为 `closed`）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原提醒规则。外部套件 `$ValidationRoot/tests/runtime_domains/test_customer_care.py`（9 项），run `20260928T134415Z-01d36b4163` passed。详见 `docs/implementation-checkpoints/M7-6-2-review-v1.md`。源码指纹 `a880c46be8eb7a42afbb943bdba43d567555404122c1972691e94f3bfd87204d`。下一项 M7.6.3。

### M7.6.3 客户提醒来源

**状态**：implemented（2026-09-28 实现并完成外部实测；7 项通过）

**全局顺序前置**：M7.6.2 done。

**验证状态**：映射/快照/两条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/care_reminder.py`（`CareReminderAdapter`，`object_types=('reminder_rule',)`：快照只读 `GET /api/customer-service/reminders/rules`，**集合读取按真实 ID 精确匹配**（同名不同 ID 不匹配，找不到即 404），未登记 kind 502，动作可用性一律 `unknown`；`extract_result` 覆盖规则保存与生成写接口（清单读不绑定结果）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `reminder.rule_active`（原 `active=true` 且 ID 精确匹配）、`reminder.generated_case_recorded`（**原读法不暴露周期/来源与已生成案件关联时一律未知，不从文字/日期自行断言已生成**）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未调用原生成写接口。外部套件 `$ValidationRoot/tests/runtime_domains/test_care_reminder.py`（7 项），run `20260928T134539Z-db53035e2c` passed。详见 `docs/implementation-checkpoints/M7-6-3-review-v1.md`。源码指纹 `68e6089bbfa2eaba873ffe4ef4dd38ca720e5b1c5d6378bac9b1f1c4972dde97`。**遗留**：已生成关联需评审补只读路径。下一项 M7.7.1。

## M7.7 会员、本金、权益与套餐

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-7-1"></a>

### M7.7.1 会员业务单

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.6.3 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/membership_order.py`（`MembershipOrderAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/membership/orders/{key}`，**key 一律取原 `Case.id`**（显式拒绝用 `MembershipOrder.id` 替代 → 502），未登记 purpose 422，动作可用性一律 `unknown`；`extract_result` 覆盖会员族 operation；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `membership.executed`（**原执行事件与原单状态必须吻合**，只有其一即未知）、`membership.fee_refund_basis_recorded`（原 `MembershipEvent.action='fee_refund_basis'`；**原权限脱敏时仍承认事实但不替原权限开口**）、`membership.period_linked`（原结果明确关联实际周期，未提供即未知）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原状态机。外部套件 `$ValidationRoot/tests/runtime_domains/test_membership_order.py`（8 项），run `20260928T134722Z-58418d55d4` passed。详见 `docs/implementation-checkpoints/M7-7-1-review-v1.md`。源码指纹 `985c6bd47496c7fdc5c7cf4c11d194d6e921ed09850907406299d2fb4750f4a5`。下一项 M7.7.2。

### M7.7.2 集团本金与权益

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.7.1 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/group_principal.py`（`GroupPrincipalAdapter`，`object_types=('group_member',)`：快照单次只读 `GET /api/group/members/{member_id}`，ID 不一致 502，动作可用性一律 `unknown`；`extract_result` 覆盖集团会员动作 operation；`read_receipt` 走集团回执族并保持冻结 `request_id`；事实 `group_principal.entry_recorded`（原 `GroupEntry` 且保留 kind/金额与来源；**达到原 `limit(100)` 分页上限时如实说明截断**）、`group_principal.reservation_recorded`（原 `GroupReservation`；占用不代表已核销）、`group_principal.refund_recorded`（**原退款成功结果与原资金退回账目一致**；仅申请/审批返回未知）——三条都只证明存在，不当作某单已结清），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原金额公式。外部套件 `$ValidationRoot/tests/runtime_domains/test_group_principal.py`（9 项），run `20260928T134846Z-28b9dc6c02` passed。详见 `docs/implementation-checkpoints/M7-7-2-review-v1.md`。源码指纹 `acebc011468eaf5b7a1dce7ed7d804c55265bfd745fbbe3064f48c5e4ac71f92`。下一项 M7.7.3。

### M7.7.3 集团权益

**状态**：implemented（2026-09-28 实现并完成外部实测；6 项通过；**含一处接口不匹配待评审**）

**全局顺序前置**：M7.7.2 done。

**验证状态**：注册范围、不匹配处理、写结果绑定与回执合同已实测；**权益快照与三条事实在映射补齐前无法验证**。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/group_benefit.py`（`GroupBenefitAdapter`，`object_types=('group_member',)`）。**接口不匹配（如实登记）**：已评审权益读取 `GET /api/group/benefits/members` 的必填参数是 **`customer_id`**（原签名 `def member(customer_id:int, ...)`），与本项登记的 `group_member` 维度不一致；按合同"缺必要 ID 返回无法建立依赖证据、不让模型猜 ID"，`read_snapshot` 返回 503 并给原页面入口（**套件断言零读取**），三条事实一律未知并说明原因，绝不自行拼接客户 ID 或改用未评审映射。可判定部分照常实现：`extract_result` 绑定原动作响应中的会员、`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；四种原 KINDS（bonus/points/coupon/package）与三条 operation 均已在 reviewed catalog 内逐一登记，`fallback_object_types=()`。外部套件 `$ValidationRoot/tests/runtime_domains/test_group_benefit.py`（6 项），run `20260928T135007Z-fafb1eff0f` passed。详见 `docs/implementation-checkpoints/M7-7-3-review-v1.md`。源码指纹 `a3064809caea4d1c998aadef28178bfc94dc17a3a556d676672248383d6d07a1`。**待评审**：补 member→customer 已评审只读映射，或改本项对象类型为客户维度。下一项 M7.7.4。

### M7.7.4 组合退回与履约

**状态**：implemented（2026-09-28 实现并完成外部实测；8 项通过）

**全局顺序前置**：M7.7.3 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/recharge_bundle.py`（`RechargeBundleAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/recharge-bundles/orders/{key}`，**key 一律取原 `Case.id`**（显式拒绝用订单自身 id 替代 → 502），未登记 purpose 422，动作可用性一律 `unknown`；`extract_result` 覆盖组合族 operation（只读购买清单不绑定结果）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `recharge_bundle.purchase_recorded`（原 execute 结果指向原 `RechargeBundlePurchase` 且有可识别 id；一笔不代表整单结清）、`recharge_bundle.refund_posted`（原 `RechargeBundleRefundPosting`；**未提供过账标记即未知**，不把退款申请当过账）、`recharge_bundle.cancelled`（原状态确为 `cancelled`）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原组件与金额公式。外部套件 `$ValidationRoot/tests/runtime_domains/test_recharge_bundle.py`（8 项），run `20260928T135125Z-b3855d9148` passed。详见 `docs/implementation-checkpoints/M7-7-4-review-v1.md`。源码指纹 `a58a284c690dac1a36f34a9a6c3b7c55bee1c829f77f1453ab0a2825ee6fc22b`。下一项 M7.7.5。

### M7.7.5 维修套餐

**状态**：implemented（2026-09-28 实现并完成外部实测；6 项通过；**含一处读取维度不匹配待评审**）

**全局顺序前置**：M7.7.4 done。

**验证状态**：注册范围、不匹配处理、写结果绑定与回执合同已实测；**套餐购买的快照与三条事实在映射补齐前无法验证**。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/repair_package.py`（`RepairPackageAdapter`，`object_types=('package_purchase',)`）。**读取维度不匹配（如实登记）**：本领域已评审读取只有 `GET /api/repair-packages/members/{key}/purchases`（按会员），**无按购买 id 的详情读取**（套件断言目录中 `GET /api/repair-packages/purchases*` 为空）；按合同"缺必要 ID 返回无法建立依赖证据、不让模型猜 ID"，`read_snapshot` 返回 503 并给原页面入口（**零读取**），`repair_package.issued`/`capture_recorded`/`refund_paid` 三条事实一律未知并说明原因，绝不自行拼接会员 ID 或改用未评审查询。可判定部分照常实现：`extract_result` 绑定原写接口返回的购买、`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；七条已评审 operation 与 `fallback_object_types=()` 均登记。**实测修正**：首轮套件用源码字符串扫描校验注册，因实现改用常量而失败；已改为 Spy 校验注册表（更强），产品代码未改。外部套件 `$ValidationRoot/tests/runtime_domains/test_repair_package.py`（6 项），run `20260928T135316Z-d145c0ca9b` passed。详见 `docs/implementation-checkpoints/M7-7-5-review-v1.md`。源码指纹 `3b49bf9a12cedde422882b0e4ac99924e950198f3884ee2901be8e942946d60f`。**待评审**：补 purchase→member 只读映射或按购买 id 的读取。下一项 M7.7.6。

### M7.7.6 会员价格规则

**状态**：implemented（2026-09-28 实现并完成外部实测；9 项通过）

**全局顺序前置**：M7.7.5 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/member_price.py`（`MemberPriceAdapter`，`object_types=('member_pricing_rule',)`：快照单次只读 `GET /api/member-pricing/rules/{key}`，**key 即原规则 id**（与对象类型一致），动作可用性一律 `unknown`；`extract_result` 覆盖规则族 operation（候选读不绑定结果）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `member_price.approved`（原 `MemberPricingDecision` 为批准；提交/驳回不满足，缺动作类型即未知）、`member_price.cancelled`（原状态确为 `cancelled`）、`member_price.authorization_recorded`（必须原 `MemberPricingAuthorization` 关联本规则冻结报价快照；**候选存在不证明已应用/已授权**，未提供即未知）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原价格公式。外部套件 `$ValidationRoot/tests/runtime_domains/test_member_price.py`（9 项），run `20260928T135434Z-03b787be6f` passed。详见 `docs/implementation-checkpoints/M7-7-6-review-v1.md`。源码指纹 `f12ab9a34e3aa6036c5659f98069fa3b0b3b6a5a0725fa2bbab3a289c871a0fa`。下一项 M7.8.1。

### M7.8.1 预收与结算

**状态**：implemented（2026-09-28 实现并完成外部实测；7 项通过）

**全局顺序前置**：M7.7.6 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/business_finance_order.py`（`BusinessFinanceOrderAdapter`，`object_types=('case',)`：快照单次只读 `GET /api/business-finance/orders/{key}`，**key 一律取原 `Case.id`**（显式拒绝用 `FinanceOrder.id` 替代 → 502），动作可用性一律 `unknown`；`extract_result` 覆盖财务族 operation（来源读不绑定结果）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `finance.executed`（**原执行事件与原状态必须吻合**；只有其一即未知；理由保留原 purpose 且明确"执行成功不代表所有款项完成"）、`finance.cash_batch_recorded`（原 `FinanceCashBatch` 及分配）、`finance.correction_recorded`（原 `FinanceCorrection` 或明确更正结果）——**后两键依 purpose 选择实际存在的原事实，不适用/未提供时返回 unknown 而非 False**），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原金额公式。**实测拦截/修复**：首轮 7 项低于派生登记的 8 项下限，被 `below_registered_minimum` 如实判不完整；按实际规模对齐为 7 后通过（未虚增断言）。外部套件 `$ValidationRoot/tests/runtime_domains/test_business_finance_order.py`（7 项），run `20260928T135629Z-7d6fb61959` passed。详见 `docs/implementation-checkpoints/M7-8-1-review-v1.md`。源码指纹 `ba748f5b4030bde5a1f9b78d89df53840388ed3a0db8886fc9015ca396dc8882`。下一项 M7.8.2。

### M7.8.2 发票

**状态**：implemented（2026-09-28 实现并完成外部实测；7 项通过）

**全局顺序前置**：M7.8.1 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/invoice.py`（`InvoiceAdapter`，`object_types=('case',)`（`InvoiceApplication.id` 与原 Case.id 相同）：快照单次只读 `GET /api/invoices/orders/{key}`，**缺原来源单 502**（不补默认值），动作可用性一律 `unknown`；`extract_result` 覆盖发票族 operation（来源读不绑定结果）；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `invoice.submission_recorded`（原对外提交记录；**详情未提供即未知**，不据文字/日期断言；满足时明确"提交不等于开票成功"）、`invoice.result_recorded`（原 `InvoiceResult`；**failure/difference 仍是原结果但不代表发票已开具**）、`invoice.result_reviewed`（原 review_result 复核事实；未提供即未知；明确"复核不改变原开票结果本身"）），`__init__.py` 显式注册且 `fallback_object_types=()`；未新增 signal hook、未改原余额公式。外部套件 `$ValidationRoot/tests/runtime_domains/test_invoice.py`（7 项），run `20260928T135748Z-2a3ce40540` passed。详见 `docs/implementation-checkpoints/M7-8-2-review-v1.md`。源码指纹 `306fb1da92501149609e4eb94d42c4e05c448c20a477eed3eef9d9714e92e267`。下一项 M7.8.3。

### M7.8.3 月结冻结

**状态**：implemented（2026-09-28 实现并完成外部实测；7 项通过）

**全局顺序前置**：M7.8.2 done。

**验证状态**：映射/快照/三条事实/回执合同在隔离夹具中通过；真实原库与真实模型属 M8.x。

**执行记录**：2026-09-28 新增 `app/assistant_runtime_domains/reconciliation_batch.py`（`ReconciliationBatchAdapter`，`object_types=('reconciliation_batch',)`：快照单次只读 `GET /api/reconciliation/batches/{key}`（**key 即原批次 id**），ID 不一致 502，动作可用性一律 `unknown`；`extract_result` 覆盖只读批次与写路径；`read_receipt` 由已评审 resolver 绑定并保持冻结 `request_id`；事实 `reconciliation.sealed`（原 `status='sealed'`）、`reconciliation.superseded`（原状态被取代，理由带后继批次并明确**取代不冲销原差异记录**）、`reconciliation.issue_recorded`（原 `ReconciliationIssue`，理由给出条数与未解决条数并明确**issue 存在不等于差异已解决**）），`__init__.py` 显式注册（import/`__all__`/`operation_ids` 三处含 `POST /api/reconciliation/batches` 与批次动作）且 `fallback_object_types=()`。**实测发现并修复**：① 我据截断输出误判"无写 operation"，套件失败后按完整目录修正为登记真实写路径；② 一次补丁把字面 `\n` 写进源码，`ast.parse` 立即拦截、仓库未被污染，已还原；③ 首次安装的"已注册"跳过导致 spec 缺写 operation，已显式补齐；④ 直改覆盖层套件被 `VALIDATION_REJECTED:overlay_addition_changed` 拒绝（冻结机制按设计生效），重新登记哈希后通过。外部套件 `$ValidationRoot/tests/runtime_domains/test_reconciliation_batch.py`（7 项），run `20260928T140158Z-7bdbde8e27` passed。详见 `docs/implementation-checkpoints/M7-8-3-review-v1.md`。源码指纹 `7f77ae424f3698ad0a45a77d7a5447678b627eb33db2406597ac2c2c8117d9ea`。下一项 M7.9.1。

### M7.9.1 整车库存与仓储统计查询

**状态**：todo

**全局顺序前置**：M7.8.5 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `inventory_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/inventory_reports_api.py`、`app/vehicle_operations_analytics.py`、`app/vehicle_procurement_service.py`。

**允许改**：新文件 `app/assistant_runtime_domains/inventory_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_inventory_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/inventory-reports/{kind} 和 /warehouses/options/{kind}；只读报表，无写入动作。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/inventory_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；仅冻结原 inventory-reports GET 的 kind/筛选及原查询结果，不注册任何库存完成、交车或入出库事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：冻结员工筛选/期间/仓库范围，保留原响应列、数量与来源引用；原 kind 由目录选择。
3. 接统一只读回执 resolver：read_receipt 返回 unsupported（本项只有 GET）；query_snapshot 不作为业务完成证据。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：未知 kind 明确输入错误；跨店汇总仅本人授权门店；不得制造可点击写入捷径或自动导出文件。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_inventory_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.1
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-9-2"></a>

### M7.9.2 物资期间入出存查询

**状态**：todo

**全局顺序前置**：M7.9.1 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `stock_period_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/stock_report_api.py`、`app/stock_reports.py`、`app/warehouse_period_analytics.py`。

**允许改**：新文件 `app/assistant_runtime_domains/stock_period_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_stock_period_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/stock-reports/period；date_from/date_to 与原库位/物资筛选完全沿 API schema。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/stock_period_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；仅冻结原 stock-reports/period GET 的原期间/筛选及结果，期末数字不生成库存交接完成事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：期间期初/入/出/期末、来源定义、未知成本 null；查询参数和观察时间入快照。
3. 接统一只读回执 resolver：仅 GET，read_receipt=unsupported。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：不得重复加总同一 StockMove/库位来源；未知成本不能零填；不同期间查询不得复用旧 WorkItem 结果。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_stock_period_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.2
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-9-3"></a>

### M7.9.3 实际维修领退料分析

**状态**：todo

**全局顺序前置**：M7.9.2 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `repair_material_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/repair_material_api.py`、`app/repair_material_analytics.py`、`app/repair_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/repair_material_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_repair_material_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/repair-material-reports；case_id/item_id/date_from/date_to 来自原 schema。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/repair_material_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；只读原维修领退料统计结果，不以无报表行推定领料、施工或结清完成。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：只读真实领退料与原成本来源，不使用报价计划数量代实发。
3. 接统一只读回执 resolver：仅 GET，read_receipt=unsupported。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：原退回/原成本可追溯；统计权限限制保留；没有报表行不推定施工结束或库存已结清。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_repair_material_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.3
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-9-4"></a>

### M7.9.4 物资收入成本对照

**状态**：todo

**全局顺序前置**：M7.9.3 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `material_value_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/material_value_api.py`、`app/material_value_analytics.py`、`app/retail_bundle_analytics.py`。

**允许改**：新文件 `app/assistant_runtime_domains/material_value_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_material_value_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/material-value；其余聚合由原服务计算；不调用 /export。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/material_value_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；原收入/成本查询结果只供解释与比较，不生成收入确认、付款或出库完成事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原收入/成本定义、套餐分摊与期间范围；仅显示服务端既有统计。
3. 接统一只读回执 resolver：仅 GET，read_receipt=unsupported。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：原成本 null 不改0；套餐组成与分摊只读；不能把采购付款直接当本期出库成本。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_material_value_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.4
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-9-5"></a>

### M7.9.5 售前活动及维修进出厂统计

**状态**：todo

**全局顺序前置**：M7.9.4 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `visit_activity_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/visit_activity_api.py`、`app/gate_visit_reporting.py`、`app/customer_service.py`。

**允许改**：新文件 `app/assistant_runtime_domains/visit_activity_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_visit_activity_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/visit-activity-reports；范围/期间按原 API。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/visit_activity_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；保留原访问/到离厂统计口径，聚合数字不生成某辆车已到厂或离厂事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：真实跟进、预约、实际到厂、实际离场和纠正来源分别统计。
3. 接统一只读回执 resolver：仅 GET，read_receipt=unsupported。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：预约不计实际进厂；取消维修不能算已离厂；同源记录不重复计数；只解释原口径不修改定义。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_visit_activity_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.5
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-9-6"></a>

### M7.9.6 原经营汇总与日报查询

**状态**：todo

**全局顺序前置**：M7.9.5 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `management_report` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/main.py`、`app/reports.py`、`app/flow_analytics.py`、`app/business_assistant_gateway.py`。

**允许改**：新文件 `app/assistant_runtime_domains/management_report.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_management_report.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/dashboard、/api/reports、/api/reports/{report_id}、/api/flow/analytics；生成日报 POST 在 CLASSIFIED_BLOCKED_WRITES。

**注册合同**：object_type=report_query（本人 WorkItem.id）；daily_report（原 DailyReport.id）；adapter=`app/assistant_runtime_domains/management_report.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；dashboard/analytics/list 使用 report_query，已有单份日报 GET 使用 daily_report。日报存在/生成时间不代表现金、库存或外部手续完成。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：日报版本/原期间/是否 provisional 与真实摘要；历史报表保持原定义。
3. 接统一只读回执 resolver：仅 GET，read_receipt=unsupported；已存在 DailyReport 使用原 report_id。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：助手未配置仍可读授权结果；不给普通销售管理页面内容；查询日报不触发日报生成/外发 AI 合同。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_management_report.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.9.6
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

## M7.10 跨店调拨、异常与原单授权

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-10-1"></a>

### M7.10.1 跨店物资调拨

**状态**：todo

**全局顺序前置**：M7.9.6 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `material_transfer` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/transfer_api.py`、`app/transfer_service.py`、`app/transfer_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/material_transfer.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_material_transfer.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/transfers/{key}；requested/approved/transit/completed/cancelled；dispatch/receive/return_ship/return_receive。

**注册合同**：object_type=material_transfer（MaterialTransfer.id）；adapter=`app/assistant_runtime_domains/material_transfer.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`material_transfer.dispatch_recorded`：本单原 TransferMovement 的 dispatch 来源；`material_transfer.receive_recorded`：本单原 receive movement；`material_transfer.return_receive_recorded`：本单原 return_receive movement。保留 line_id/数量及双方店，至少一行记录不代表整批齐收。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：双方批准、每行实际发收/退运/退回、在途及来源数量。
3. 接统一只读回执 resolver：TransferReceipt，transfer_service.execute；冻结请求内发起店与 actor。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：双方本店身份分别查询；部分签收保留每行未结；禁止改 store_id 或用源店权限代目的店签收。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_material_transfer.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.1
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-10-2"></a>

### M7.10.2 跨店整车调拨

**状态**：todo

**全局顺序前置**：M7.10.1 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `vehicle_transfer` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/vehicle_transfer_api.py`、`app/vehicle_transfer_service.py`、`app/vehicle_transfer_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/vehicle_transfer.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_vehicle_transfer.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/vehicle-transfers/{key}；requested/approved/transit/rejected/return_transit/accepted/returned/cancelled/lost/recovered；原 dispatch/accept/return_ship/return_receive。

**注册合同**：object_type=vehicle_transfer（VehicleTransfer.id）；adapter=`app/assistant_runtime_domains/vehicle_transfer.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`vehicle_transfer.accepted`：原状态 accepted 且原 accept/VehicleMovement 对应同 VIN；`vehicle_transfer.returned`：原状态 returned 且原 return_receive/原车移动事实吻合；`vehicle_transfer.lost`：原详情原状态 lost。rejected 不能满足 returned。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原 VIN、实际 custody/movement、两店任务及实物接收结果。
3. 接统一只读回执 resolver：TransferReceipt；vehicle_transfer_service 复用 transfer_service.execute 的原 operation 摘要。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：拒收不等于退回原店；在途不能配售；原车找回不直接当新车入库；跨店返回只显示原授权投影。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_vehicle_transfer.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.2
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-10-3"></a>

### M7.10.3 物资运输差异及损失处置

**状态**：todo

**全局顺序前置**：M7.10.2 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `transfer_exception` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/transfer_exception_api.py`、`app/transfer_exception_service.py`、`app/transfer_exception_models.py`、`app/transfer_exception_recovery.py`。

**允许改**：新文件 `app/assistant_runtime_domains/transfer_exception.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_transfer_exception.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/transfer-exceptions/{key}、/origins/{transfer_id}；observe/plan/approve/reject_plan/dispose/post_loss/cancel。

**注册合同**：object_type=transfer_exception（TransferException.id）；adapter=`app/assistant_runtime_domains/transfer_exception.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`transfer_exception.observation_recorded`：本单原 TransferExceptionObservation；`transfer_exception.disposal_recorded`：本单原 TransferExceptionDisposal；`transfer_exception.loss_posted`：本单原 TransferLossPosting。方案批准不等于处置或过账。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：实际 missing/damaged 观察、双方独立复核、实际处置/原损失及赔付目标来源。
3. 接统一只读回执 resolver：TransferExceptionReceipt，_execute；摘要包含真实异常原单和方案版本。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：两店独立复核缺一保持 waiting；已批准处置不等于实际损失过账或赔款到账；任何未知赔付不重放。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_transfer_exception.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.3
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-10-4"></a>

### M7.10.4 原损失物资查找与找回

**状态**：todo

**全局顺序前置**：M7.10.3 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `transfer_goods_recovery` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/transfer_goods_recovery_api.py`、`app/transfer_goods_recovery_service.py`、`app/transfer_goods_recovery_models.py`、`app/transfer_goods_search_service.py`。

**允许改**：新文件 `app/assistant_runtime_domains/transfer_goods_recovery.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_transfer_goods_recovery.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/transfer-goods-recoveries/{key}；match/inspect/ship/receive/plan/approve/reject/dispose/restore/finish_bad；unlocated 不等于 recovered。

**注册合同**：object_type=goods_recovery（GoodsRecovery.id）；adapter=`app/assistant_runtime_domains/transfer_goods_recovery.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`goods_recovery.match_recorded`：本案原 match 成功结果及 GoodsFact 的明确原损失匹配；`goods_recovery.receipt_recorded`：本案原 receive 成功结果及实物接收 GoodsFact；`goods_recovery.restore_posted`：本案原 restore 成功结果及 GoodsPosting。找到/收到不能替代损失恢复过账或赔付退回。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原损失、真实找到/保管、另一店独立匹配、实物处理与原赔付后续分别核对。
3. 接统一只读回执 resolver：GoodsReceipt；trace_open/trace_approve/trace_reject/refind 等仍由原 goods execute 包装处理，read_receipt 不查 GoodsSearch 当请求回执。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：错误关联可按原路退出；找回不自动冲销损失或收回赔付；残值/返运/不可用逐原事实等待。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_transfer_goods_recovery.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.4
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-10-5"></a>

### M7.10.5 整车运输异常与原车找回

**状态**：todo

**全局顺序前置**：M7.10.4 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `vehicle_transport_exception` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/vehicle_transport_api.py`、`app/vehicle_transport_service.py`、`app/vehicle_transport_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/vehicle_transport_exception.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_vehicle_transport_exception.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/vehicle-transport-exceptions/{key}；observe/observe_found、plan_resume/plan_found、dispose/post_loss/found_receive/found_unavailable。

**注册合同**：object_type=vehicle_transport_exception（VehicleTransportException.id）；adapter=`app/assistant_runtime_domains/vehicle_transport_exception.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`vehicle_transport.loss_posted`：本案原 VehicleTransportLoss；`vehicle_transport.found_received`：本案原 VehicleTransportFoundReceipt 且原 VIN 一致；`vehicle_transport.found_unavailable_recorded`：本案原 VehicleTransportFoundUnavailable。计划找回不满足实际找到/接收键。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：真实原 VIN、异常观察、双方方案/审查、原损失与原车找回验收。
3. 接统一只读回执 resolver：VehicleTransportReceipt，vehicle_transport_service.execute 的 action+values；FoundReceipt 仅找回业务事实。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：VIN 不匹配不得换车冒名；失而复得仍走原保管/验收；无实际找到事实不准备 found_receive。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_vehicle_transport_exception.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.5
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-10-6"></a>

### M7.10.6 跨店原单档案授权

**状态**：todo

**全局顺序前置**：M7.10.5 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `dossier_grant` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/dossier_grant_api.py`、`app/dossier_grant_service.py`、`app/dossier_grant_models.py`、`app/dossier_grant_rules.py`。

**允许改**：新文件 `app/assistant_runtime_domains/dossier_grant.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_dossier_grant.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/dossier-grants/{grant_id} 和 /record；原 propose/decide/read_record 保留源店审批和指定接收人。

**注册合同**：object_type=dossier_grant（DossierGrant.id）；adapter=`app/assistant_runtime_domains/dossier_grant.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`dossier.approval_recorded`：本授权原 DossierDecision 批准；`dossier.record_readable`：当前 principal 通过原 /record 成功读取相同 grant 的原授权摘要；`dossier.revocation_recorded`：原撤回/撤销决定明确存在。批准历史不满足当前可读，403/404 无法区分不存在和不可见时为 unknown。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原授权版本、范围摘要、源单版本和现时 recipient/access_version；后台只读已授权 record。
3. 接统一只读回执 resolver：DossierReceipt，含 action/request_data/grant_id/scope_digest；原详情重新验权后才返回。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：不开放 files/download 到模型；授权过期/撤回/原人员权限变化立即 waiting(permission_lost)；不把授权当业务执行。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_dossier_grant.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.10.6
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

## M7.11 基础资料和系统管理边界

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-11-1"></a>

### M7.11.1 类型化基础资料

**状态**：todo

**全局顺序前置**：M7.10.6 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `typed_master` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/master_api.py`、`app/master_data.py`、`app/master_models.py`、`app/business_assistant_gateway.py`。

**允许改**：新文件 `app/assistant_runtime_domains/typed_master.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_typed_master.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/masters/catalog、/api/masters/{kind}、/lookup/{kind}；写入只按原已评审 POST/PUT 与 CATALOG schema。

**注册合同**：object_type=vehicle_brand、vehicle_series、supplier、insurer、warehouse、storage_location、material_brand、material_category、master_work_item、team、agency_project、vehicle_model、member_tier、item_profile（均为原 CATALOG 对应实体主键）；adapter=`app/assistant_runtime_domains/typed_master.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`master.record_exists`：原对应 kind 的授权详情/完整分页精确命中该 ID；`master.active`：同一原记录 active=true，缺字段为 unknown。类型与 kind 固定字典映射，原业务作业 WorkItem 映射为 master_work_item，不混为 Runtime WorkItem。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：客户/供应商/保险公司/车型/仓库/库位等明确 type+真实 ID/version；同名候选返回真实中文 label。
3. 接统一只读回执 resolver：MasterReceipt；原 save_master 包装的 kind/create/update 摘要；不得用任意 ORM 表名查。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：保留真实停用守卫；缺必填关系先 needs_input，不建更多卡凑数；opening-import 和模板原始内容保持手工。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_typed_master.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.11.1
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-11-2"></a>

### M7.11.2 业务分类字典

**状态**：todo

**全局顺序前置**：M7.11.1 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `dictionary_entry` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/dictionary_api.py`、`app/master_data.py`、`app/business_assistant_capabilities.json`。

**允许改**：新文件 `app/assistant_runtime_domains/dictionary_entry.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_dictionary_entry.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/dictionaries/catalog、/api/dictionaries/{group}；可准备写入仅以真实 router 和 reviewed capabilities 交集为准。

**注册合同**：object_type=dictionary_entry（原 flow Reference.id；原 category 固定映射 dictionary group）；adapter=`app/assistant_runtime_domains/dictionary_entry.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`dictionary.record_exists`：原指定 group 授权列表精确命中 Reference.id；`dictionary.active`：该原记录 active=true。原条目字段为 name/detail/active，不把自然语言标签猜成业务 value/状态枚举。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原 group、稳定 key/value/label 与有效性，不把显示中文换成原 API 枚举。
3. 接统一只读回执 resolver：MasterReceipt；dictionary_api.save 复用 master_data._command，action=dictionary:<group>，payload 为 id/version/values。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：未知 group、更新版本冲突、非管理岗位拒绝保留；字典只维护名称说明和启停，不改变业务状态/岗位/计价规则。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_dictionary_entry.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.11.2
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-11-3"></a>

### M7.11.3 系统管理的原授权查询与人工入口

**状态**：todo

**全局顺序前置**：M7.11.2 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `system_readonly` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/main.py`、`app/parameter_api.py`、`app/user_access_service.py`、`app/business_assistant_gateway.py`。

**允许改**：新文件 `app/assistant_runtime_domains/system_readonly.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_system_readonly.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/users、/api/stores、/api/audit、/api/parameters/catalog；MANAGEMENT_READERS 与 CLOSED_DOMAINS 是现有边界。

**注册合同**：object_type=report_query（本人 WorkItem.id）；adapter=`app/assistant_runtime_domains/system_readonly.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`fact_keys=[]`；仅保留允许的 users/stores/audit/parameters 注册 GET 结果与原手工入口。查询权限配置不产生授权生效、密码变更或员工创建完成事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：只读账号/门店/审计/参数入口的原授权结果；输出人工页面路由，不读取凭据/部署 settings。
3. 接统一只读回执 resolver：仅只读适配，read_receipt=unsupported。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：普通销售不可读账号列表；新员工不默认管理员/全门店；参数、账号权限/密码/门店配置写入回原页面，不扩 reviewed capabilities。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_system_readonly.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.11.3
```

**勾选验收**：

- [ ] 原查询结果/筛选/权限与原页面一致；没有生成业务卡、调用写接口或改变业务行。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 无原生版本返回 null，report_query 不被付款/实物完成条件接受。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-11-4"></a>

### M7.11.4 真实拒绝记录与评审申请跟踪

**状态**：todo

**全局顺序前置**：M7.11.3 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `escalation_request` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/escalation_api.py`、`app/escalation_service.py`、`app/escalation_models.py`、`app/business_assistant_gateway.py`。

**允许改**：新文件 `app/assistant_runtime_domains/escalation_request.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_escalation_request.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/escalations/refusals 与 /api/escalations；只准备 POST /api/escalations；claim/done/reject/cancel 是原人工处理动作。

**注册合同**：object_type=escalation（Escalation.id）；refusal（Refusal.id）；adapter=`app/assistant_runtime_domains/escalation_request.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`escalation.request_recorded`：原授权列表精确匹配 Escalation.id 与服务器 refusal_id；`escalation.done`：原人工 done 动作及当前原申请状态吻合；`escalation.refusal_recorded`：原 /refusals 精确匹配 Refusal.id/classification。前两键仅适用 escalation，末键仅适用 refusal；评审 done 不满足业务成功或权限已授予。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：服务器真实 refusal_id/classification、当前店上级队列和本人申请状态；无单项 GET 时从已授权分页列表准确匹配。
3. 接统一只读回执 resolver：原提交没有 request_id 保障，read_receipt=unsupported；未知提交保持 uncertain，不重复申请。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：自批禁止/状态冲突不包装权限不足；评审通过不改变权限或执行业务；不可代上级处理，回原页面。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_escalation_request.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.11.4
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 现有非幂等评审提交未知结果必须人工核对，测试明确不自动重提。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

## M7.12 保险、加装和代办专用服务

本组只作目录，下列小项才是可领取、实施和打勾的任务。

<a id="m7-12-1"></a>

### M7.12.1 保险报价、外部承保与原款退回

**状态**：todo

**全局顺序前置**：M7.11.4 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `insurance_order` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/insurance_api.py`、`app/insurance_service.py`、`app/insurance_models.py`、`app/insurance_finance.py`。

**允许改**：新文件 `app/assistant_runtime_domains/insurance_order.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_insurance_order.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/insurance-orders/{case_id}；quote/review/authorize/submit/result/receive/disburse/direct_paid/termination/refund/commission_review 等见 LABELS。

**注册合同**：object_type=case（InsuranceOrder.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/insurance_order.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`insurance.current_quote_consented`：当前原报价有 InsuranceConsent，引用同 quote_id/digest；`insurance.external_result_recorded`：本单原 InsuranceResult 及原 submission_id/outcome；`insurance.policy_issued`：原结果 outcome=issued 且真实 policy_number 存在。任意外部结果不能满足已出保；保费/佣金保持各自原资金事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：当前保单报价/授权、保险公司实际结果、代收代缴/直付直退、实际佣金各自来源。
3. 接统一只读回执 resolver：InsuranceRequest/insurance_requests，沿 insurance_service._execute 的原 action/payload 摘要。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：代收保费不能算收入；客户直付不制造本店现金；撤保批准不等于退保/退款已实际发生；外部补件保持 waiting。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_insurance_order.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.12.1
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-12-2"></a>

### M7.12.2 销售明细加装与原物资退回

**状态**：todo

**全局顺序前置**：M7.12.1 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `addon_order` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/addon_api.py`、`app/addon_service.py`、`app/addon_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/addon_order.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_addon_order.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/addon-orders/{key}；quote/approve/authorize/dispatch/install/quality/rectify/accept/receive/resolution/return_receive/refund 等见 service:23。

**注册合同**：object_type=case（AddonOrder.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/addon_order.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`addon.installation_recorded`：本单原 AddonInstallation 关联真实 dispatch_id；`addon.passed_inspection_recorded`：本单原 AddonInspection.passed=true 且对应实际安装；`addon.current_quote_accepted`：当前报价有原 AddonAcceptance。单批合格不能冒充整版全部完成，处置变更后必须重读原事实。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：原销售版本、冻结加装行、领出安装/质检/客户接收、原款与拆回物资实际来源。
3. 接统一只读回执 resolver：AddonReceipt，addon_service._execute。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：报价改变先重核关系；赠送成本承担保留原店；客户授权不等于实际安装；退回不可售物资不自动入可售库存。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_addon_order.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.12.2
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

<a id="m7-12-3"></a>

### M7.12.3 代办及其他客户服务

**状态**：todo

**全局顺序前置**：M7.12.2 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：只完成 `service_order` 一个适配器，将本项原系统能力接到统一快照、结果引用、事实等待及安全回执合同。

**现有必读**：`app/service_orders_api.py`、`app/service_orders_service.py`、`app/service_orders_models.py`。

**允许改**：新文件 `app/assistant_runtime_domains/service_order.py`、`app/assistant_runtime_domains/__init__.py` 中本项显式注册映射、外部 `$ValidationRoot/tests/runtime_domains/test_service_order.py` 及 M0 manifest 的本编号登记。原业务文件默认不改；小 signal hook 仅按共同合同第 10 条，在上述 service 的原成功事务中追加。

**禁止改**：原业务动作/状态/岗位/门店/版本/幂等/金额数量公式及迁移；不改原API响应，不新增自动确认，不将本项以外业务顺带重构。

**原生证据**：GET /api/service-orders/{case_id}；subtype=agency/other_income；quote/approve/authorize/submit/external_result/fulfill/receive/disburse/termination/refund。

**注册合同**：object_type=case（ServiceOrder.id 与原 Case.id 相同）；adapter=`app/assistant_runtime_domains/service_order.py`，在 `app/assistant_runtime_domains/__init__.py` 显式注册。有限事实键及原满足条件：`service.submission_recorded`：本单原 ServiceSubmission；`service.external_approved`：原 ServiceExternalResult.outcome=approved 且对应当前原项目最新提交；`service.fulfillment_recorded`：本单原 ServiceFulfillment 及 line_key。至少一项履约不代表全部项目或款项完成。

**实施步骤**：

1. 按上列原 GET 和 schema 实现 read_snapshot；检查详情与列表是否有区别，集合查询必须按真实 ID 精确匹配并处理分页。动作只保留原返回可用性；未知版本/无原版本按共同合同处理。
2. 为本项确切 operation_id 实现 extract_result；注册事实快照：服务费/代收代付行、实际外部提交/结果、实际履约、原款代缴/退回与终止方案分别输出。
3. 接统一只读回执 resolver：ServiceRequest/service_requests，沿 service_orders_service._execute 的原 operation/payload 摘要。 使用冻结的最终提交快照，不能重新生成请求号；无回执不得猜成功。
4. 将下述异常做成确定性夹具；仅新增本 adapter 的注册元数据和事实名，复用核心准备/等待/事件处理，不创建本领域 Agent 或第二状态机。

**状态转移与异常路径**：外部 need_documents/rejected 不完结；代缴款不并入服务收入；实际办结与实际收款分别等待，未知退款不重放。 按共同合同第 7 条分别进入 waiting/needs_input/awaiting_confirmation/uncertain；只有原事实满足才 completed。

**命令**（新增 suite：`$ValidationRoot/tests/runtime_domains/test_service_order.py`）：

```powershell
& $ValidationPython "$ValidationRoot/run_validation.py" --repo "$RepoRoot" --milestone M7.12.3
```

**勾选验收**：

- [ ] 在隔离夹具中“读取→准备→测试员工点击原确认→重读事实”通过；卡片准备本身不产生业务写入。
- [ ] 本项所列具体异常有断言；重复事件/重启不重复准备；岗位或门店撤权后不暴露旧结果。
- [ ] 原 native result 与回执类型正确；缺回执/失权/摘要不符均不能把步骤标为完成。
- [ ] 当前源码指纹、suite、数据库类型、日志和未验证项已记录；未把历史成绩或仅结构通过计为业务闭环。

## 业务适配整体收口（不是额外实现任务）

由主实施计划的整体验收项检查：52 个小项状态逐项可见；193 项需求和 111 条工作流仍映射到原入口、原能力及这些适配器；没有把尚未接 adapter 等同于原业务被删除。额外报告每个 operation 的 read/prepare/fact/receipt/manual 边界；unsupported 只用于确实只读或原生无可靠回执的核对能力，不能用来批量豁免本应支持的准备功能。

多领域长链的端到端验收属于后续集成项，不要求每个小 adapter 重复承担整个销售/维修/跨店系统的验收。每个单项仍必须完成其真实业务闭环或正确等待/拒绝，并保持原 API 为唯一业务权威。

<a id="m8-1"></a>

## M8.1 综合故障与恢复验收

**状态**：todo

**全局顺序前置**：M7.12.3 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证已完成各子系统接在一起后，不重复准备、不越权、不丢批量项，不把未知结果变成自动重试。

**依赖**：schema/迁移、确认冻结、回执适配、后台身份、WorkItem/队列、计划/上下文、发件箱/跟进、通知及业务适配对应里程碑done且各自定向测试passed。

**读/写边界**：读取`app/assistant_runtime_*.py`、`app/assistant_worker.py`、原assistant service/gateway/security及已实现对象适配；只写V/tests/runtime_faults、合成故障夹具和证据。发现源码缺陷回到其所属实现里程碑修复，本项不得顺手重构。

**允许/禁止**：允许在独立子进程中注入中断、延迟、重复事件和模型协议异常；禁止向生产进程发信号、伪造真实业务回执或降低断言。

**步骤**：依次覆盖重复request_id/唤醒、双worker竞争、过期租约晚写、准备提交前后崩溃、批量每个行边界崩溃、半截JSON/重复toolID、确认冻结后中断、业务已提交但助手未落结果、回执not_found/unsupported/mismatch、发件箱重复/乱序/分发中断、通知失败、退出及撤权、取消/过期卡、无变化等待、摘要事实过期、目标版本变化。每个故障记录注入点、恢复动作、原生事实前后hash及完整行结果。

**状态转移与异常路径**：超时或未恢复不得算通过；原生回执不可核对时应保持uncertain并阻塞依赖，作为正确行为通过该断言，而非宣称业务成功。权限错误不得按网络错误退避。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.1`

**完成检查**：
- [ ] 确认前原业务写入0，资金/库存等重复事实0。
- [ ] 每个稳定WorkItem最多一个对应有效准备版本；批量无遗漏。
- [ ] 旧租约不能覆盖新状态；无授权/撤权不能继续或泄露结果。
- [ ] “业务成功、通知失败”仍呈现真实业务成功；未知写入绝不重放。
- [ ] 故障重复执行能稳定得到同一断言结果。

<a id="m8-2"></a>

## M8.2 原业务、助手和前端不退化验收

**状态**：todo

**全局顺序前置**：M8.1 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：覆盖保留的193项需求映射、111条发布工作流、原业务接口及新旧助手兼容。

**依赖**：所有业务族/界面/兼容实现完成，M8.1 done。

**读/写边界**：读取当前app/web、`docs/requirements.json`、workflow-source及M0.2归档测试清单；写V/tests/regression、manifest和逐项报告。仓库仅写验收记录，业务修复回所属里程碑。

**允许/禁止**：允许按真实API变化更新外部测试调用方式；禁止删业务、改原需求名、放宽权限或把只读目录覆盖计为交易闭环。

**步骤**：重新执行M0.2全部仍适用测试及各实现项新增测试；审查全部193需求入口/原名搜索/岗位/原API映射；生成工作流检查；检查原十模块入口、原消息/流式/确认/取消/批量/MCP协议与旧数据阅读；按领域解释任何缺失或变化，不以通过总数掩盖丢失用例。

**状态转移与异常路径**：任何原功能丢失、权限退化、静默未收集测试使测试failed、里程碑保持in_progress；工作流源缺失为blocked。193映射全部有记录不等于193业务已验收。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.2`

**完成检查**：
- [ ] 基线及新增用例逐项比较，新增/缺失/不适用均有理由。
- [ ] 193映射与111工作流检查通过，原菜单及原名搜索仍可用。
- [ ] SQLite当前适用原业务/助手/前端自动回归全部通过。
- [ ] 旧接口返回合同保留，相同request_id不产生第二Run。

<a id="m8-3"></a>

## M8.3 SQLite与真实PostgreSQL升级、并发和备份恢复

**状态**：todo

**全局顺序前置**：M8.2 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证从h52j合成旧库升级、完整性守卫及两种数据库上的运行时并发语义。

**依赖**：迁移/备份实现、M8.1–M8.2 done；显式提供独立真实PostgreSQL测试服务。

**读/写边界**：读取`migrations/`、`app/backup_integrity.py`、原私有附件备份服务、新runtime完整性检查；仅写外部全新SQLite合成库、专用PG测试库、合成附件和备份目录。绝不复制生产/预览库来“更真实”。

**允许/禁止**：允许在有合成标记的专用新库建表、迁移和恢复；禁止在未验证DB身份前执行DDL，禁止降级删除新业务数据。PG URL凭据不进入日志。

**步骤**：建立h52j合成旧库并放旧消息/卡/计划/原业务事实；记录逐表行hash；升级到唯一新头，验证旧行及legacy默认值；注入孤儿/跨员工/跨店/循环引用；做SQLite库与合成附件联合备份并恢复到全新目录；在真实PG重跑迁移、唯一约束、乐观锁、双worker租约与事务发件箱竞态。确认生产数据库驱动版本。现有`app.cli backup`是SQLite入口，不宣称它已支持PG备份；PG部署必须另有已评审的原生数据库备份+合成附件联合恢复流程并在独立新库验证，缺该流程则记录此项blocked，不以SQLite恢复替代。

**状态转移与异常路径**：没有真实PG、连接失败或没有专用库授权时该项blocked，即使SQLite通过也不能将里程碑标done；mock/SQLite不能替代PG。破坏旧行或跨店引用漏检使测试failed、里程碑保持in_progress。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.3`

**完成检查**：
- [ ] h52j→新头唯一、可重复验证；原业务行和旧记录完整。
- [ ] 旧计划没有自动启动；恢复不补造确认冻结证据。
- [ ] SQLite与真实PG迁移/并发均有本轮证据。
- [ ] 联合备份恢复成功，错误引用与缺附件均被拒绝。

<a id="m8-4"></a>

## M8.4 真实HTTP浏览器、安全会话与界面验收

**状态**：todo

**全局顺序前置**：M8.3 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证真实浏览器直接访问隔离Web服务的Cookie/CSRF/CSP/SSE及员工操作体验。

**依赖**：界面/认证/事件API完成，M8.1–M8.3 done；可运行真实浏览器与隔离HTTP/HTTPS服务。

**读/写边界**：读取当前web、真实HTTP安全配置和路由；写V/browser、tests/frontend、本次合成浏览器截图/日志。只启合成数据服务，截图不能含客户资料。

**允许/禁止**：允许真实登录、原确认点击、切店、退出、断网/重连和浏览器重启；禁止通过ASGI桥接或mock cookie冒充真实浏览器链路，禁止关闭CSP/CSRF来通过。

**步骤**：在390/768/1440宽度检查默认助手、有效深链接、原模块/待办/指引；输入中文及组合输入，后台事件到达时检查焦点/光标/未发文字/补填答案；覆盖同组批量失败暂停、旧卡、换店迟到结果、退出清理；断开SSE后重连按seq补读，确认Run继续；验证伪造内部身份header无效、缺CSRF写被拒绝、Cookie及CSP满足对应环境；模型故障仍可用原业务。

**状态转移与异常路径**：无法直接导航隔离服务则blocked，并记录桥接结果仅作辅助；UI静态截图不能替代交互。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.4`

**完成检查**：
- [ ] 真实HTTP/HTTPS会话、CSRF、CSP、SSE证据齐全。
- [ ] 三种宽度、中文输入、草稿与答案保护通过。
- [ ] 单张/同组确认仍须员工点击，失败即暂停。
- [ ] UI状态均来自服务器真实记录，原人工入口始终可用。

<a id="m8-5"></a>

## M8.5 原101/283真实模型回归

**状态**：todo

**全局顺序前置**：M8.4 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：对当前实现取得真实模型报告，保留原场景口径与历史结果区别。

**依赖**：M8.1–M8.4 done；原场景和冻结定义完整；用户显式允许本轮付费live调用、外部私有配置、实际额度和网络。

**读/写边界**：读取当前provider适配/工具schema、归档101/283定义与冻结提示词；仅写V/live-evaluation定义适配及本轮脱敏报告。不得改历史场景、成绩或使用真实客户数据。

**允许/禁止**：允许真实DeepSeek/MiMo调用已配置固定端点；禁止静默fallback、将probe/Mock算生成评测、把prepared卡数当业务闭环分数。默认演练无外网。

**步骤**：先离线生成评测清单，锁定源码/提示词/schema/场景hash及调用预算；明确101开发复测与283全量重叠，报告独立case与请求次数；取得live gate后运行归档入口对应测试；逐例审阅语义、对象、事实、批量完整性、额外追问、工具调用及耗时；DeepSeek与MiMo分别记录，某provider未实测不能称两者实测通过。

**状态转移与异常路径**：缺密钥/付费授权/额度/网络、触及预算后未跑完、缺报告均blocked；模型实际业务错误使测试failed、里程碑保持in_progress。只完成结构检查不能将本项标done。

**命令**：
```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.5
```
runner先检查外部live gate；缺失则仅生成清单并标blocked，不自动付费。gate具备后，调用被审过的原`test_assistant_live.py --live --suite all --transport sse --output <本次外部报告>`等manifest命令，provider/预算由gate明确指定，不通过命令行传密钥。

**完成检查**：
- [ ] 报告证明真实生成请求、目标provider及本次源码指纹。
- [ ] 101/283不重复计总量，不覆写历史R2/R3成绩。
- [ ] 结构及语义逐例审阅，金额/数量/对象/越权关键错误0。
- [ ] 批量各行有结果，失败和未运行场景均明确记录。

<a id="m8-6"></a>

## M8.6 多轮闭环与未调参保留集验收

**状态**：todo

**全局顺序前置**：M8.5 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证从目标到员工确认、真实事实变化和后续准备的连续办理，而不是仅验证卡片生成。

**依赖**：M8.5 done；真实模型外部条件保持有效；独立保留集在候选冻结后由未参与提示词调参者封存。

**读/写边界**：读取当前业务能力矩阵和已通过的合成业务适配测试；写V/live-evaluation/multiturn、holdout、审核记录及合成实际写入证据。保留集不要存进提示词源码。

**允许/禁止**：验收脚本可以在合成环境通过原确认接口模拟员工已审阅点击，但模型本身不能调用确认；禁止把测试脚本确认能力暴露成工具。不能边调参边继续宣称同一套案例是保留集。

**步骤**：六类主要业务链各至少5个多轮场景，覆盖正常、缺项/消歧、多人协作、事实变化、失败恢复；逐步确认后核对原生流水/原单/任务，并测试持续跟进开启与未开启差异；另执行至少60条未调参员工表达，逐例判定正确办理或正确等待/拒绝；保留集发现缺陷后可修复，但该集合转为开发集，重新封存独立保留集后再给最终比例。

**状态转移与异常路径**：无独立保留集或真实模型调用受阻为blocked；结构passed但事实/权限/重复写入错误使测试failed、里程碑保持in_progress。外部事实尚不存在时正确等待可以通过相应场景，不伪造到账/到货。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.6`

**完成检查**：
- [ ] 至少30条新多轮链有实际确认与事实核对证据。
- [ ] 至少60条独立保留表达，语义正确办理/等待/拒绝≥95%。
- [ ] 越权、未确认写入、重复资金/库存事实、金额/数量/对象关键错误均0。
- [ ] 不将该保留集比例表述为全公司业务成功率。

<a id="m8-7"></a>

## M8.7 Windows隔离预览启动、关闭和恢复

**状态**：todo

**全局顺序前置**：M8.6 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证Windows预览与worker共享同一明确实例，启动/退出/休眠恢复不丢委托、不串库。

**依赖**：Windows启动及worker功能实现，M8.1–M8.6 done；可执行隔离Windows预览环境。

**读/写边界**：读取`start-preview.cmd`、`start-preview.ps1`、`scripts/preview_launcher.ps1`、`start.ps1`、worker及功能开关；写V/deployment/windows和外部合成实例。不得启动/修改用户原预览实例、账号或数据。

**允许/禁止**：允许通过当前启动脚本启动隔离副本和隐藏后台辅助进程；禁止改日报开关、重置原账号、借用公司配置或用仅unit mock代替进程恢复。

**步骤**：干净合成实例正常启动并验证Web/worker DB标识一致；双次启动不重复worker；开启与暂停grant、普通即时run、退出登录分别验证；终止worker再起、关闭应用再起、模拟机器不可用后到期补查；分别关闭新首页/运行/跟进/通知开关验证原业务可用；异常端口、错误路径、缺迁移时明确失败。

**状态转移与异常路径**：缺Windows执行面为blocked；跨实例串库或退出后即时run仍执行使测试failed、里程碑保持in_progress。机器睡眠期间不能运行必须如实呈现，不承诺离线机器持续执行。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.7`

**完成检查**：
- [ ] Web/worker实例及源码指纹一致，原预览未触碰。
- [ ] 重启、关闭、缺迁移及开关组合有真实进程证据。
- [ ] 委托恢复不重放业务，普通即时run遵守登录状态。
- [ ] 退出后受托查询准备符合产品选择，撤权即时停止。

<a id="m8-8"></a>

## M8.8 Linux独立worker部署与恢复演练

**状态**：todo

**全局顺序前置**：M8.7 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：验证真实Linux部署的独立Web/worker、健康状态、重启恢复和配置隔离。

**依赖**：Linux部署文件和worker实现，M8.7 done；独立Linux测试机/容器、合成数据库、明确服务配置。

**读/写边界**：读取`Dockerfile`、`compose.yml`、`start.sh`、实际新增worker服务说明及`app/assistant_worker.py`；仅写V/deployment/linux证据及独立Linux合成实例。禁止SSH/部署公司服务器或修改既有服务。

**允许/禁止**：允许运行真实Linux进程/容器并模拟终止；禁止用Windows-only结果代替Linux、把健康HTTP200等同后台任务健康、执行破坏性迁移降级。

**步骤**：使用本次source镜像建立Linux实例，Web/worker共享相同代码配置与合成DB；运行worker `--once`、常驻模式、双worker争抢；验证心跳/队列积压/最后成功时间，终止及重启恢复；演练HTTPS/安全Cookie/明确Host/ClamAV及legacy write禁止的生产配置校验；关闭新功能后原业务读取/操作仍可用，保留所有既有事实。

**状态转移与异常路径**：没有真实Linux、TLS/ClamAV等所需环境时记录对应blocked，不能称生产验收通过；代码/配置问题使测试failed、里程碑保持in_progress。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.8`
runner将本轮安全镜像及不含凭据的执行清单交给已提供的Linux验证入口；只接受带同一source fingerprint的回传结果，缺执行环境不得模拟passed。

**完成检查**：
- [ ] 真实LinuxWeb/worker运行、`--once`、健康与重启证据齐全。
- [ ] 双worker无重复准备，旧租约无晚写。
- [ ] 生产必需配置单列通过/blocked，无“源码包开箱即生产”结论。
- [ ] 回退为功能开关，不删除计划/原单/流水，不降级破坏数据。

<a id="m8-9"></a>

## M8.9 员工试用与效率验收

**状态**：todo

**全局顺序前置**：M8.8 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：确认员工实际完成高频任务更省事，业务人员认可等待、拒绝与协作表达。

**依赖**：M8.1–M8.8 done；用户安排真实销售/服务顾问/库管/财务/店长代表和试用时间；默认仍用专门合成验收环境。若进入真实单店试用，另有明确部署与数据授权，不由本计划自动执行。

**读/写边界**：读取已冻结场景、能力矩阵和新旧界面；只写V/employee-acceptance脱敏任务记录/时间/操作统计/员工结论。不得收集客户原资料、聊天内容或真实截图作为默认证据。

**允许/禁止**：允许员工用原页面与助手各完成同一组合成任务；禁止以开发者自测代替员工验收、挑选少量有利案例或把等待客户/到货时间计入节省时间。

**步骤**：固定任务与角色、交叉安排先后顺序；记录有效操作时间、点击/填写次数、追问和回退次数；复核结果是否事实正确；收集需要原页面协作的业务；中位有效操作时间至少降低20%，同时守住关键正确性0错误；反馈修改后只重测受影响项及必要回归，不覆盖原记录。

**状态转移与异常路径**：无人实际参与为blocked，不替员工填写认可；速度达标但正确性失败使测试failed、里程碑保持in_progress，不能上线。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.9`
runner只核验事先录入且可追溯的员工验收记录及计算指标；没有真实记录时输出blocked，不自动生成意见。

**完成检查**：
- [ ] 指定岗位员工实际参与，记录对应版本及任务。
- [ ] 中位有效操作时间较原页面降低≥20%，口径排除外部等待。
- [ ] 关键正确性守卫通过；真实反馈、缺陷及复测可追溯。
- [ ] 实际试用范围和未验收领域清楚，不扩大结论。

<a id="m8-10"></a>

## M8.10 发布门槛、交付包与回退清单

**状态**：todo

**全局顺序前置**：M8.9 done。

**执行记录**：完成日期=—；修改文件=—；源码指纹=—；测试结果=未执行；命令/退出码=—；证据路径=—；遗留/阻塞=—。


**目标**：将源码实现、自动验证、真实模型、运行环境及员工验收分别核实，再形成可评审的发布候选。

**依赖**：全部要求的实现里程碑及M8.1–M8.9 done，无未解决关键缺陷；真实发布另外遵循用户部署授权。

**读/写边界**：读取manifest全部结果、当前源码/迁移/工作流、`scripts/package_source.py`、README/交接/检查点；允许仅按下述规则更新`scripts/package_source.py`根文档精确白名单，更新仓库交付说明和事实检查点、外部release-gate报告及源码包。不得提交/打包真实env、密钥、DB、证据附件、日志、备份或客户截图。

**允许/禁止**：允许更新`scripts/package_source.py`的根文档白名单，仅新增`total_plan.md`、`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`implementation_plan.md`、`ASTRA_LOW_EXECUTION_PROMPT.md`、`DEEPSEEK_HANDOFF.md`、`DEEPSEEK_EXECUTION_PROMPT.md`这7个精确文件名；AGENTS.md沿用原必要文档规则。保留现有所有数据/凭据排除策略，不扩大任意根文件或E盘目录入包。允许生成仓库外包并扫描内容、hash和迁移完整性；禁止从未通过候选上宣称已上线，不执行公司生产迁移/部署或破坏性回滚。

**步骤**：逐项审计所有状态与源码指纹，过期报告不直接继承；核验要求的0错误项、95%保留集、20%效率指标，确认M0.2的baseline_defects全部关闭；确认完整迁移和四个默认关闭的功能开关；更新打包根文档精确白名单并生成源码包，检查这7份文件均存在且大小写准确；检查公开包仅含当前安全源码/必要文档/完整迁移，不含V、归档E盘测试、测试数据库、日志、模型报告、截图或员工记录。文档写清“已实现/已验证/待部署”和真实外部限制；提供新环境备份→迁移副本验证→恢复验证→小范围部署→扩大范围的发布检查表，以及仅关功能的回退步骤。

**状态转移与异常路径**：任一强制里程碑非done或其要求的测试blocked/failed则发布gate不通过：外部条件缺失使M8.10 blocked，发现需本项修复的问题保持in_progress；不得将里程碑写成failed/passed。可以交付开发源码，但显式标“未达发布门槛”，不能把文档记录完成当软件验收完成。

**命令**：`& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M8.10`
manifest内部调用本次镜像的`python scripts/package_source.py --output <外部唯一包路径>`（若该工具依赖Git，使用只读当前工作树打包并对照本轮fingerprint），然后审计包；不得让打包依赖去读取旧source或私有数据。

**完成检查**：
- [ ] 每项强制验证有当前候选证据，外部条件没有假通过。
- [ ] 源码包无敏感材料，完整迁移及原193需求/111工作流保留。
- [ ] 7份根文档精确入包且保留AGENTS.md；E盘外部测试、fixture、日志、报告、截图和员工材料全部不入公开源码包。
- [ ] M0.2基线缺陷备案全部关闭，四个新开关代码默认false。
- [ ] 检查点分开记录实现、自动测试、真实模型、员工和部署状态。
- [ ] 发布顺序与功能开关回退可执行，生产动作尚需其真实授权与环境。
