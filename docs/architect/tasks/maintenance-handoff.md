# 维护交接整理

目标：按业主指令整合main、保持Cutie修复和原界面改动，整理代码职责及关键架构注释，使独立环境和其他模型可维护；本地真实模型复验保留，取消的部署/独立OS项目不恢复。

当前状态只查 [实施计划M8.5](../../../implementation_plan.md#m8-5)；维护成果查 [维护交接](../../维护交接.md) 和 [M8-10审阅](../../implementation-checkpoints/M8-10-maintenance-review-v1.md)。维护完成不代替模型验收。

本轮观察、修复范围和逐次结果集中记录于 [本地复验补丁](../../implementation-patches/PATCH-M8-5-LOCAL-LIVE-01.md) 与 [模型审阅](../../implementation-checkpoints/M8-5-mode-comparison-review-v1.md)。旧B04豁免已撤回，所有原件与历史失败保留；原进度文字可从Git 26c7b41追溯。

root负责源码、计划、Git和付费执行；三个只读审阅分片合并前各核实际案例SHA，regression_harness另核五指纹、进程终态和累计账本。代理不修改活动验证的源码或输入。

接下来按原计划先完成当前真实模型定向和全量，再进入后续原验收项。最终从实际交付树刷新源码/验证材料，核对无凭据、数据库和日志，推送main。员工试用与人工验收由相应人员完成，不能据代码、结构检查或历史成绩代签。

2026-10-06追加：业主明确切本地复验至`deepseek-flash`，累计上限350元。当天[官方更新日志](https://api-docs.deepseek.com/updates/)及[人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)标明当前为V4.1 Flash，峰时命中/未命中/输出0.04/2/8元每百万token，单POST保守预留5.242880元。生产默认、thinking/high接线和Runtime适配器无需修改；root只登记外部helper的历史费用分段、私有gate及指纹绑定，并先执行新strict。旧280元上限是历史条件，不改写旧报告。

旧3984条费用保守占230.037690元（已结算163.715258元、七条未知66.322432元），不重价、不释放；helper按1—1402旧Flash、1403—3984旧Pro、3985起新Flash核原行政策。前1402条旧Flash不能因本次官方版本映射被改称另一后台版本。拟先新strict和原F[complete]接口同步定向验证，再八例S01/S08/V03/X03/F02/B03/HELP021/HELP041，随后从零完整283/101；均为待执行，M8.5仍in_progress、CP-37 not_ready，M8.6未开始。

2026-10-06后续：Flash八代表真实及语义8/8，完整队列在10/283出现S03/05/06三个问题后持预算锁停止并自然排空，旧报告保留。root集成原单指导与按动作员工候选；业务审阅分片核原岗位合同，界面分片同步搜索上下文，验证分片仅扩原节点及有限代表ID。代码完成不预记复验；当前状态仍只查M8.5。
