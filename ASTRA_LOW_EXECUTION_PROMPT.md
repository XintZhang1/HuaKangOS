# Astra low 实施指令（兼容入口）

> 历史入口，当前执行入口为 CODEX_EXECUTION_PROMPT.md；用户已授权 Codex 直接按 implementation_plan.md R3 实施。下方 DeepSeek 交接与人工逐批停止规则仅保留历史。

2026-09-27更新：用户改为交接DeepSeek，并要求中途强制停下审阅。完整实施指令统一维护在`DEEPSEEK_EXECUTION_PROMPT.md`，本文件保留原文件名供已有任务引用。相同规则也适用于Astra low。

可复制：

```text
阅读AGENTS.md、DEEPSEEK_HANDOFF.md和DEEPSEEK_EXECUTION_PROMPT.md，按其中要求再读PROJECT_SPEC.md、ARCHITECTURE.md和小写implementation_plan.md。
执行相同的单milestone和人工checkpoint规则，不因当前模型名称不同改变范围。
首次只执行implementation_plan.md的M0.2.A，完成后停在CP-00A，保存审阅报告，等待用户审阅补丁或明确放行。
不得开始M0.2.B完整基线或M0.3，不得依据旧目标模式指令自动跨checkpoint。
如果此前已到checkpoint，先核对唯一门禁表和用户放行记录，不重做初始批次。
补丁默认仅授权修补并复测，完成后仍停同一CP；只有用户明确放行才能进入下一批。
```

旧版“一项done后自动由后续目标轮次进入下一项”的无条件规则已废止。现在只允许在已放行批次内部按数字索引串行推进；到检查点必须结束执行。
