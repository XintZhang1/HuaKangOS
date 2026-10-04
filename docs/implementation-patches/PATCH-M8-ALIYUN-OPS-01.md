# PATCH-M8-ALIYUN-OPS-01：阿里云试运行及后台运维队列

日期：2026-10-03。依据：业主本轮明确要求先部署 HuaKangOS，再实现 aliyun + DeepSeek 意见收集和自动运维队列；context/memory、阿里云 MCP、Workflow Engine 均需实际接线，改动邮件交 Cutie review、改代码、提交 GitHub PR，业主合并。业主选择独立试运行 + SSH 隧道，并提供仓库外 DeepSeek 凭据供部署后实测。

本轮新授权优先于旧文档关于“不部署/不联网模型/不新增运维”的范围限制；不把它扩大为自动改业务数据、自动编码、自动合并或自动发布。原 M8 正式验收与四业务开关默认关闭保持，原 M8.1 仍是唯一 in_progress 项。本补丁作为当前独立交付范围，不修改 total_plan.md、不重写旧成绩。

## 设计及范围

- 阿里云全新 `/opt/huakangos` 源码发布目录、`/etc/huakangos` 私有配置、`/var/lib/huakangos` 全新试运行库与运维状态；仅 loopback 监听，经 SSH 隧道访问。保留其他服务和所有既有数据，不从本机预览库复制业务数据。
- 意见入口是唯一新增前端功能；原员工会话、CSRF、当前门店权限校验，显式告知意见会交 DeepSeek 和 Cutie。意见不读取客户档案或自动附带业务数据。
- 独立后台运维 agent，不借用业务助手工具/员工业务 Runtime。固定 DeepSeek endpoint；只读代码上下文按发布清单/哈希、有限工具读取，持久 memory 记录有出处的结论及 review 结果，不保存原始推理。
- 持久队列 Workflow Engine：领取/租约、分析检查点、改动建议、邮件 outbox、失败/不确定结果。分析进程无 Git 推送、shell、任意文件、业务写入或发布工具。Cutie 获取当前任务后独立 review、改代码、提 PR；业主保留合并权。
- 复用阿里云既有 Cutie MCP/邮件服务，确有接线缺口时增加独立运维 MCP 工具和限定服务配置，不覆盖原状态服务。

允许文件：`app/ops_*.py`、`app/main.py`（路由接线）、`web/feedback.js`、`web/app.js`（意见入口）、`web/index.html`（脚本接线）、必要新增迁移、`app/models.py`（仅模型注册，如需要）、`scripts/huakangos_ops*.py`、`scripts/huakangos-ops*.example`、`scripts/aliyun_trial*.py`、`docs/architect/tasks/aliyun-ops.md`、本补丁、部署交接文档及 `implementation_plan.md` 当前项附记/任务索引。必要依赖只在确定实现需要时补齐。

## 异常与验收

云端通道核对后补充精确范围：`scripts/huakangos_ops*.mjs`、`docs/huakangos-ops-mail.md`；独立 `huakangos-ops-mail.service` 复用已存在的 QQ SMTP 发送器和系统凭据注入，不修改既有 dsh 状态服务。独立邮件 MCP 有固定收件人、限定提案结构及外置持久 outbox；不是新增任意发信或阿里云 DirectMail 功能。意见及运维状态保存在新外置 SQLite，原业务 schema 无需迁移，备份时需另备份运维库及邮件 outbox。

反馈重复提交按请求标识去重；无授权/跨店拒绝；源码上下文不得逃逸清单或读取秘密；模型输出及用户意见均作为不可信内容；网络结果不明不盲发邮件；任务恢复不能重复通知或把失败当成功。数据库/配置/日志/截图/凭据均留仓库外。

先部署当前候选并验证健康/登录，再实施意见到模型分析到 MCP/邮件的真实路径。新实现以外置合成库、代表反馈、实际 DeepSeek 与邮件服务留证；明确区分邮件服务接受和 Cutie 实际处理。不得把本轮试运行等同公司生产验收。
