# DeepSeek 集中测试与修复交接

交接协议：2026-09-28，配套 `implementation_plan.md` 的 `R4-20260928` 及后续授权补丁。

用户要求先由 Codex 完成项目实现，再统一交给 DeepSeek 测试与修复。**本文件现在只保存待测合同；用户实际转交测试任务后才启动测试阶段。** 旧 `DEEPSEEK_HANDOFF.md`、`DEEPSEEK_EXECUTION_PROMPT.md` 和 Astra 提示词是历史实施交接，不是本阶段入口。

## 1. 接手先读

1. `AGENTS.md`、`CHECKPOINT_STATUS.json`、`README.md`。
2. `PROJECT_SPEC.md`、`ARCHITECTURE.md`。
3. `implementation_plan.md` 共同规则、当前状态、各项原验收条件和检查点表。
4. 对应 `docs/implementation-checkpoints/` 报告、`docs/implementation-patches/` 补丁及实际涉及代码。
5. 本文件的历史基线和未测条件。

不要按本文件建立第二套实施状态。接手时以计划中的最新记录和实际源码为准，不能假设当前已完成所有实现。

## 2. 状态与范围

| 标记 | 含义 | 测试阶段处理 |
|---|---|---|
| `implemented` | 代码已实现并经过代码审查，规定测试未完成 | 执行原全部验收，失败修复并复验，通过后才记 `done` |
| `done` | 当时源码满足该项全部验收 | 保留历史证据；对最终候选按原综合回归要求重新核对 |
| `todo` + `validation: deferred_to_deepseek` | 纯测试、演练或真实环境任务后移 | 按原依赖执行，不能因“交接完成”改成通过 |
| `implementation_released` | 只放行过后续编码 | 补齐该 CP 的原测试条件，实际满足后才记 `released` |
| `blocked` | 当前阶段存在真实实现/环境/验收阻塞 | 记录原因和缺少的条件，不降标准、不虚构通过 |

所有原定向测试、受影响回归、状态转移和异常路径、最终完整回归、真实模型、独立 PostgreSQL、真实浏览器、Windows/Linux 演练及员工试用要求都保留。不是只测试新文件，也不是只处理已知符号链接一项。

## 3. 已有基线：只作为历史证据

权威历史报告：`docs/implementation-checkpoints/CP-00B-v5.md`。报告和旧 run 原样保留；后续编码放行不修改其“当时未满足完整验收”的结论。

- 完整 B run：`20260927T163618Z-574f417642`，41 条命令实际执行。
- 实际合计：**3336 passed / 0 failed / 1 skipped**；pytest 为 2780 passed、1 skipped，其他检查 556 passed。
- 上一完整轮的 **36 个失败已经在该完整 B 逐项闭合**。不要重新称它们仍未解决。
- 清单没有 missing、extra、duplicate、not_run 或超时；但 1 项 skip 使原完整 B 判定仍失败，不可称“全量通过”。
- 193 项目录检查只是静态帮助查询，不等于 193 项业务已验收。该轮真实模型调用为 0。
- 原报告中的源码、测试、执行器和依赖指纹属于当时快照；之后 Codex 的新代码没有因该成绩自动通过。

旧基线唯一未执行的原安全断言来自：

```text
tests/test_private_files.py::test_symlink_file_and_root_rejected
```

该节点在创建文件符号链接时进入 OSError/skip；文件链接读取拒绝和目录链接根拒绝两条原断言均未执行。本轮没有具体 Windows 错误码，不能把早期独立探测的 WinError 1314 冒写为该完整轮观测。

后续必须在能真实创建文件和目录符号链接的授权隔离环境执行原断言。不能改成 passed、不适用或 xfail，也不能用硬链接、目录联接或删断言代替。用户后移测试并未授权修改 Windows 开发者模式、OS 用户权限或系统安全设置；条件仍缺失时如实记录待解决的验收条件，不反复运行同一长基线。

## 4. 环境与入口

当前验证根为：

```text
V = C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1
Python = V/.venv/Scripts/python.exe
Runner = V/run_validation.py
```

- V 位于 NTFS；原 `E:/HuaKangOS-agent-validation/runtime-v1` 只保留历史证据，不搬走或改写旧 run。
- 清理归档：`E:/HuaKangOS-cleanup-20260927-082922/removed`；已有恢复、原件和适配差异优先复用，不能无理由重建全部环境。
- 历史 M0.2 完整 B、strict 和独立审阅证据位置见 CP-00B-v5；后续测试新增 run 与递增报告，不覆盖旧记录。
- 先核对现有 manifest、suite 注册、依赖与源码镜像规则，再按各项原合同补充尚未编写的测试；所有测试和证据仍在 V。
- 统一 runner 安全镜像当前白名单源码，设置合成库和附件根之后才能导入 app；不能直接导入工作树 app 作“只读检查”。
- 主数据库必须是标记的仓库外新合成库；辅助匿名 `:memory:` 保持原内存语义。不能接公司库、用户原预览库或真实附件。
- 不读取真实 `.env` 或把密钥写入代码、日志及报告；离线 provider 必须禁止外部调用。

统一命令形式（**只在接手测试阶段使用**）：

```powershell
$RepoRoot = (Resolve-Path '.').Path
$V = 'C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'
$VPython = "$V/.venv/Scripts/python.exe"
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone Mx.y
```

`Mx.y` 替换为正在验证的单项；M0.2 的阶段参数按原合同使用。不要假设尚未登记的 suite 或命令已经存在，也不要绕过 runner 得出验收结论。

## 5. 执行顺序

1. 核对工作树、所有实现记录、实际接口和当前进程；找出待测范围。已有验收记录不能当新源码的证据。
2. 按计划依赖逐项补齐外部定向测试，覆盖正常流、非法转移、冲突/未知结果、暂停恢复、权限和幂等；保留原验收阈值。
3. 每次验证一个 milestone。失败先判断产品缺陷、过时合同、测试适配或环境问题；按当前项允许生产文件范围修复，必要时追加精确补丁并更新记录。
4. 对实际修改运行对应定向与受影响回归；不删失败、缩减样本或降低断言求绿。超出当前允许生产范围或根本架构冲突时报告，不重设计。
5. 完成原 CP 全部条件后保存真实审阅报告、测试结果及指纹；再将相应项记 `done`、CP 记 `released`。代码审查与静态检查不能代替运行证据。
6. 逐项检查后仍执行 M8 原综合及最终候选验收，覆盖原业务与所有新实现，不能把各次不同指纹的零散成绩拼成一次最终通过。
7. 真实环境、模型和人员条件不足时只写实际缺项；最终交付明确通过、失败、跳过及未运行，未完成全部验收不能宣称生产可用。

纯测试项后移没有取消它们的依赖。只有已实现所需代码、满足原测试前置条件后才执行对应场景；不能用空接口、Mock 或自评替代原真实环境要求。

## 6. 必须保留的业务和验收边界

- 员工本人、当前门店权限与原业务 API 是权威；助手不能自动确认或制造收付款、库存、签回等事实。
- 原状态机、幂等、版本、事务、钱量单位与跨店原单/文件授权不改；批量不承诺整批回滚，未知结果不自动重放。
- 四个新功能开关默认关闭，只在独立合成验收环境按用例显式开启；不改原预览或公司实例。
- 既有本地 DeepSeek 调用授权可在原 live gate 使用，新合成数据、调用数量及结果必须有记录；禁止真实客户数据外发。无需因为旧授权仍有效而反复请求相同权限，但额外 OS 变更或生产操作不在其中。
- 101/283 旧口径、真正多轮场景、保留集、语义人工核对和员工体验指标保留；结构分不能冒充业务完成率。
- PostgreSQL、真实 HTTP 浏览器、Windows/Linux、故障恢复、附件与员工试用分别报告；条件不具备不以模拟结果顶替。
- 测试修复不授权自动编码平台、Git 推送、发送消息、生产部署、重置账号或删除业务数据。

## 7. 用户转交时可用的提示词

M5.4新增站内提醒验收见`docs/implementation-checkpoints/M5-4-review-v1.md`及PATCH-M5-4-01：原源与Wake同事务、通知和分发CAS同事务、乱序/重复、真实同店本人和任务交接、纯Plan结束不清待确认原卡、同blocking Run一次提醒、真实login继续、executing三分钟加一微秒延迟核查、通知开关独立、GET只读/POST read幂等及冲突。M7引入非Case对象后必须补齐其固定原读取可见性；当前安全过滤不能算所有领域提醒已覆盖。

M5.3新增工作台与跟进控制验收见`docs/implementation-checkpoints/M5-3-review-v1.md`：首屏零会话/Grant/模型写入；原mine/open任务和集团排除；本人私有卡及计划；五项授权后计数；稳定游标、来源变更409和暂时GET失败503；未授权待继续、真实待确认文案；原Cookie/CSRF、v1结构化条件缺口、v2四动作及开关分别实测。CP-11仅编码放行，不表示真实浏览器或业务验收完成。

M5.2新增SSE/旧消息验收见`docs/implementation-checkpoints/M5-2-review-v1.md`：真实HTTP断线只停订阅、多人订阅不增加模型次数、after_seq/Last-ID/缺序及多批终态、每帧撤权、ASGI发送错误、600秒等待和原Run ID、精确原请求最终回复、累计展示改写不能重复append、Runtime关闭旧路径分别实测。原legacy流只作静态AST对照，尚非浏览器验证。

M5.1新增HTTP验收见`docs/implementation-checkpoints/M5-1-review-v1.md`。既有GET必须在关闭开关/模型配置不可用时可读；额外身份字段与query不接纳；真实登录、当前岗位、门店、原对象权限须在异步读取后仍成立；同请求幂等、取消版本与回执纯读分别实测。旧会话无Run表时run_id为null，仅有表时查询；Runtime入队不能当worker已健康运行。

M4.9新增回归见`docs/implementation-checkpoints/M4-9-review-v1.md`：原提交只执行一次、真实回执迟到恢复、任意次数未知查询不POST、当前Plan前轮遗留卡、完整Run旧unbound来源、fresh receipt与保存观察绑定、HTTP权限版本不可因ORM刷新而变更、只读GET无状态副作用、协调后重新读全部条件及恢复状态。CP-10仅编码放行，通知尚交M5.4接线；这些场景没有运行证据。

M4.7额外回归见`docs/implementation-checkpoints/M4-7-review-v1.md`：真实源事务回滚、权限跨店信号、晚到小ID、同Session多Plan分发原子性、Grant只读probe失效，以及task-only条件与合法carry_forward旧卡结果的唤醒。Runtime关闭不得访问新表；分发失败不改变已成功原业务。M4.8须联合核对信号与定时补漏指纹，不能把本项候选入队当完整无变化零调用已验收。

M4.8的四文件与最终指纹见`docs/implementation-checkpoints/M4-8-review-v1.md`。验证时必须统计真实模型/准备次数，覆盖20次无变化、signal/tick竞争、同Session多Plan、固定outcome等待本人补充、due在读取中到期、已消费proof提交后重放、合法完整batch剩余行，以及必要事实完成才结束Plan；代码静态检查不是这些用例的证据。

接手时同时阅读当前项引用的实施补丁和递增检查点报告。M4.5的原完整批量、无计划历史成果、新Plan绑定和过期lease恢复须联合验证；M4.6额外合同见`docs/implementation-patches/PATCH-M4-6-01.md`，包括每次provider真实外发前复验、跨会话高优先用户、完整工具边界让出、跨重启预算、独立心跳及唯一最终回复。源码静态审阅不替代这些用例；没有编写或运行过的suite必须实际登记补齐。

```text
阅读 AGENTS.md、PROJECT_SPEC.md、ARCHITECTURE.md、implementation_plan.md 和 DEEPSEEK_TESTING_HANDOFF.md。
现在进入集中测试与修复阶段，依据最新实际代码和计划记录工作。
按原全部验收条件补齐并执行外部测试，一次验证一个 milestone；失败在该项允许范围内修复并复验。
implemented 不是测试通过；纯测试/实环境项也必须按原计划完成，不能删除或降标准。
保留 CP-00B-v5 和旧 run；3336 passed / 0 failed / 1 skipped 仅为历史结果，原符号链接两条安全断言仍待真实执行。
全部验收满足后才记 done/released；未满足写实际缺项，不擅改架构、业务规则、系统权限或部署生产。
```
