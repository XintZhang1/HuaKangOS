# CP-00A-v3：修补完成并进入完整基线

日期：2026-09-27。计划：R3-20260927。执行与审阅：Codex；使用独立子代理复核实际证据。结论：M0.2.A 通过，CP-00A released，下一检查点 CP-00B。依据用户“按计划直接实施，不再依赖 DeepSeek/Astra low”的连续实施授权推进。M0.2 仍为 in_progress。

## 实际验证

外部根 V：`E:/HuaKangOS-agent-validation/runtime-v1`。两个命令之间未修改 manifest 或受检输入：

```powershell
& "$V/.venv/Scripts/python.exe" -B "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.1
& "$V/.venv/Scripts/python.exe" -B "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.2 --phase A
```

| 检查 | run / command | 实际结果 |
|---|---|---|
| 严格隔离自检 | `20260927T113830Z-d5de052b37` / `00-selftest-strict` | 18/18，exit 0，legacy=false |
| 两处迁移合同、配置节点、文案及行为 | `20260927T113902Z-7cf01ce103` / `a1-migrated-and-claim-tests` | 43/43；43 个唯一节点，129 条完整阶段记录；212.984 秒 |
| R3T3 离线 | 同 A run / `a2-assistant-r3t3-offline` | 39/39，实际 unittest 节点完整；26.282 秒 |
| 迁移及执行器合同 | 同 A run / `a3-anonymous-memory-migration` | 120/120：3 迁移、59 判定合同、24 隔离、34 绑定；360 条阶段记录；324.344 秒 |

全部命令 exit 0，无失败、错误、跳过、xfail、xpass、超时或缺失终态。A 的 `phase_complete=true`、`milestone_complete=false`、`incomplete_reasons=[]`。真实模型调用为 0。

完整报告在上述 `V/runs/<run_id>/run.json`、`command-results/<command_id>/` 及 `logs/`。进程已退出，核查无本批遗留 Python/Node 句柄。B 尚未执行，此处通过数不代表完整基线或业务闭环成功率。

## 修补与审阅结论

1. 报告必须有 command/run/source 身份、真实退出码及准确节点清单。collect 只读取独立报告；pytest 校验逐节点完整生命周期；script/selftest 将实际节点与全部汇总交叉核对。缺证据、重复、额外节点、跳过、xfail/xpass 及超时均拒绝。
2. 配置合同绑定本 run 的固定文件及 hash、当前 active_command_id 和准确活跃 node。三态仅向登记的配置测试节点开放；节点清理完成后撤销例外。拒绝 env 扩权、跨 run 引用和借用已结束命令；网络守卫仍拦截外连。
3. 产品 `load_config/status` 原本正确，没有扩大修改范围。生产仅修 `claimed_actions` 纯文本 helper：后续“请核对是否正确”不再遮掉前段完成宣称，ASCII 引号正确匹配。31 条句式保留原 27 条并增加 4 条，真实行为回归同时验证没有新增业务提交。
4. manifest 保持静态，runner 自动找到最近成功的同仓库 strict run；引用仅写当前 run。完整 manifest、恢复清单、适用规则、原测试、overlay、依赖声明/锁和已安装依赖均参与绑定及前后漂移检查。
5. 根执行文件更新为用户授权的 R3 直接实施方式，未改 total_plan.md 的原始计划或产品架构。

独立复核重新计算了指纹并检查实际节点，确认身份/exit/计数一致；生产 diff 只含 service 的 CLAIM 常量和相关纯文本函数，未触及对话、provider、SSE、API、RBAC、业务 schema 或迁移。

## 冻结证据

受检源码 606 个文件；harness 26 个文件；外部输入 626 个文件；overlay 314 个文件（308 个恢复原件及 6 个新增文件）。两次 run 的以下五类指纹完全相等：

| 输入 | SHA256 |
|---|---|
| source | `d42e6b8cf2223ee5f2666516cdbd544754107cb7a3805770fe07eccf152cb916` |
| harness（含完整 manifest） | `370223aac6e8572b944506cc649f5480a8f45d1e04435f0e9b746d4daf8486b4` |
| external inputs | `0b853bb57bf66262556bb97333b960e3f5e60d07b5a37aba4dd3b82fe2db49dc` |
| dependency lock | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` |
| installed dependencies | `3478e11a0a20e10ab8da26419583d9f53ea8e06daab1007beab4822f5d2373ba` |

service 文件 SHA256：`cfacf9417d40a70984cbf889f80dfac7dcd902111d47fab7e52ae099bf1575a2`。源码、镜像、overlay、harness、外部输入、manifest 快照均未变化，依赖前后相等且锁定与必需依赖检查都通过。此报告和实施状态回填发生在验证完成后，不改历史 run。

实际 diff/纯函数辅助证据：`V/review/CP-00A-v3/`；文案前后证据在 `V/review/CP-00A-v2/claim-fix/`。v1/v2 及旧失败均保留。

## 关闭与保留边界

- BASE-001 按 M0.2.A 的有限文案合同关闭；不声称解决所有自然语言表达或全部中间 SSE 展示问题。
- 配置三态不需要产品扩权；synthetic=true、空 key 的产品含义仍是 enabled 但未 ready。
- 同盘显式 UTF-8 回读成功；旧损坏原因不能归咎于 exFAT。保留 ASCII 转义、运行期解码与无 U+FFFD 断言。
- 下一阶段登记并执行完整 Python/助手/Node/workflow 基线；完整性不能用历史通过数、静态测试数量或本次 A 成绩代替。
- 真实模型授权已收到，但本阶段未使用；独立环境、员工验收和生产部署不由本报告替代。
