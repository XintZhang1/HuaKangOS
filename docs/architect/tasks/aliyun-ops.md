# 任务：阿里云试运行与后台运维助手

**任务 id 与负责人**：aliyun-ops；root 集成，repo_contract_audit 只读合同审阅，aliyun_mcp_audit 只读云端通道审阅。

**目标与交付结果**：HuaKangOS 独立部署阿里云；员工意见进入后台 DeepSeek agent，通过有代码出处的上下文、持久 memory 和工作流队列生成改动邮件；Cutie review/改动/提 PR，业主合并。仅意见收集出现在前端。

**架构依据与决定**：沿原业务权限与确认合同；新授权及精确范围见 PATCH-M8-ALIYUN-OPS-01。采用 SSH 隧道试运行，四原业务开关关闭，独立后台运维进程不具有自动编码/合并/发布能力。

**代码快照与影响范围**：起点 7a4f8722bc66029d69cdf2b35b872c85f35f0d59，工作树干净；工作分支 codex/aliyun-ops-assistant。既有反馈表保留，但当前没有反馈 API/UI；阿里云已有 dsh-codex-status 服务，尚无 HuaKangOS。

**已完成与当前位置**：基线部署到全新目录和空库，独立 Python 3.13.16、h53k 实际迁移；16项真实HTTP检查通过。意见入口及独立 ops_store/context/config/MCP/worker、限定邮件 MCP 已落盘。独立审阅复现并修复邮件并发终态竞态、补齐模型响应结构校验；邮件 bridge 修正 current 符号链接入口。原生 Chrome 登录/填写/提交/回执/导航复开、390/1440显示检查通过（1条合成意见，0页面异常）。

**下一步**：切换修正后的完整源码候选，完成既有意见的 DeepSeek 分析、真实 MCP/邮件投递以及提交候选向 Cutie 交接。

**验证与实际阻塞**：基础部署、浏览器收集、邮件桥三组隔离HTTP/合成发送器及通知并发复现/修复已验证；当前邮件桥首次真实启动发现符号链接入口退出问题，源码已修待新发布。DeepSeek真实全链及真实邮件尚待执行。证据外置 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/aliyun-trial-20261003-0112`、`aliyun-ops-20261003-01`、`runtime-v1/mail-bridge-379bef99658648abb6cd1394778000dc`；不继承公司生产、原全量业务与真实模型评测成绩。

2026-10-03 实测追加：候选 c50c456 / context ffc2d75f 的邮件 MCP 已真实启动并核对三工具；部署后HTTP/MCP安全检查33/33通过，没有新增意见或发信。首次真实 DeepSeek 分析在工具预算上限处 `tool_budget_exceeded`，原job保留needs_attention、report/mail均空，未发信。修正为向模型明确剩余预算并在最后阶段强制JSON收束；增加仅元数据的provider请求/usage事件及reviewer显式失败重试，仍不增加调用上限、不重试不明邮件。worker已停止，等待修正候选复验；未将该失败写成模型验收通过。
