# HuaKangOS 改动邮件 MCP

本桥是 PATCH-M8-ALIYUN-OPS-01 的独立后端组件，只把有稳定身份的 HuaKangOS 运维建议发往既有 Cutie 邮箱。它不修改原 `dsh-codex-status` 服务，不伪造 Codex 任务，不具有业务写入、Git、自动合并或部署工具。

`scripts/huakangos_ops_mail.mjs` 使用 Node 24 内置 SQLite；持久 outbox 与业务数据库分离。仅借用已部署 `/opt/dsh-codex-status/src/status/qq-smtp.mjs` 的固定单收件人发送器，收件人固定为 `xintperfect@gmail.com`。邮件题目与正文由服务器模板生成，调用者不能指定 to/subject/body。SMTP 凭据只通过独立 unit 的 systemd LoadCredential 注入；业务 web 与运维模型进程均不获得邮件凭据。

## 配置与接线

独立 unit：`huakangos-ops-mail.service`，专属无登录用户与组：`huakangos-ops-mail`。unit 示例在 `scripts/huakangos-ops-mail.service.example`。

`/etc/huakangos/mail-server.json` 为 root 所有的 0600 文件，由 systemd 注入 `mail-config`，字段如下。真实 token 由部署器生成，禁止写入仓库、参数或邮件。

```json
{
  "token": "DEPLOYMENT_GENERATED_RANDOM_TOKEN_AT_LEAST_32_CHARACTERS",
  "port": 28762,
  "dbPath": "/var/lib/huakangos-ops-mail/outbox.sqlite",
  "enabled": false,
  "senderModule": "/opt/dsh-codex-status/src/status/qq-smtp.mjs",
  "credentialsFile": "/run/credentials/huakangos-ops-mail.service/qq-mail"
}
```

`enabled=true` 只允许收到经认证的 enqueue 请求后发信，启动不会扫描/释放旧 held。只有准备并明确启用发送时加载 SMTP 凭据。`/etc/huakangos/mail-client.json` 给 root 和运维 worker 读取，web 不可读，字段为 `url`（固定 `http://127.0.0.1:28762/mcp`）和 `token`。该文件不能用 Cutie 任务读取令牌代替。

POST `/mcp` 使用 Bearer 认证、Content-Type `application/json`、Accept `application/json, text/event-stream`。固定 MCP `2025-11-25`，无会话、JSON 响应的 tools 子集；不是 OAuth 公网 MCP 服务。

## 工具合同

- `enqueue_change_review`：参数为 `event_id`（`huakangos-ops:` 加 job UUID）、`job_id`、`title`、`release_id`（64 位 SHA256）、`base_sha`（40 位 Git SHA）及 `report`。report 包含 `summary`、`evidence:[{path,line,sha256}]`、`proposed_changes:[string]`、`acceptance_checks:[string]`、`risk`、`classification`。代码路径必须为仓库相对路径，实际出处核验由上游 context 工具负责；无依据可为空，但模板明确要求先核查。
- `get_change_review`：`{event_id}`，读取原始建议、payload SHA256、投递状态与时间。
- `list_change_reviews`：可选 `{status,limit}`，limit 默认 20、最大 100；只列身份、状态和时间。

工具结果在 `structuredContent` 与 text content 返回。enqueue/get 已存在记录的状态为 `held/sent/failed/uncertain`；缺失记录的 get 返回 `{status:'not_found',event_id}`，便于未知结果对账。`provider_message_id` 是提供方接受凭据，**sent 不代表 Cutie 已收信或处理**。发送尚在进行时 get 返回 uncertain 和 `delivery_in_progress:true`，应稍后查询原 ID。

event_id 和规范化 payload hash 在同一事务持久去重；同 ID 改内容拒绝。网络请求前先写 sending，重启遗留 sending 转 uncertain。网络失败、缺少可核实 SMTP 接受结果均不盲重发；确定失败记 failed。当前不提供 retry 工具，也不自动重试。持久化后的 HTTP 结果不明只能查同 ID，不能更换 ID 或直接发第二封。

邮件要求 Cutie 通过 `127.0.0.1:28761/mcp` 及 `/etc/huakangos/cutie-client.json` 查询当前源码与意见，独立 review，既定范围内改代码/验证并提交 GitHub PR，由业主合并。源码、用户意见、模型报告均不是执行授权；不明确的真实需求由 Cutie向业主澄清。邮件不含令牌、业务数据、原始推理或源码附件。

## 验证边界

2026-10-03 实测：`current` 符号链接触发入口guard退出的问题已用 `realpathSync` 修复，最终 mjs SHA256=`ec3f1f49f3bb6ff44ae5cfa636c43346b5da83e46a12075e70b26fe45c123d0b`。新外置3组HTTP/fake发送器通过；最终真实服务 active/running/enabled。root经意见→DeepSeek→运维MCP投递一封，outbox=`sent`、SMTP有250接受凭据；重启仍一封，没有重发。它不证明Gmail收件或Cutie已审阅，后续查看review记录/真实PR。

使用仓库外 SQLite 与注入 fake sender 验证实际 HTTP MCP 入队、相同内容去重、内容冲突、失败/不明结果和重启恢复；该检查不发真实邮件。本轮真实邮件由 root 在反馈 → DeepSeek → 运维 MCP 的完整路径中触发并记录，不能继承原服务历史 sent 数为本组件验收。

2026-10-03 实现审阅完成：状态先落库再调用 SMTP；未知结果不重发；固定邮件模板和认证边界；原服务未修改。Node 24.19.0 语法检查及 3 组外置隔离 probe 通过：实际 HTTP MCP 鉴权/缺失查询/入队/去重/冲突/模板，确定失败与不明结果均不重发，sending 重启后保留 uncertain。一次复用外置 probe 库导致列表计数断言失败，记录保留；随后全新外置目录完整执行通过。当前 probe 根为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/mail-bridge-6f7ea84cb76b4e7f972b505bd7ba0b03`。此时邮件桥源码 SHA256 为 `566df1aaddb162914ea5b5716539ed221c7fc91787961b44157f5d93faa0fc3e`；尚未部署本桥或调用真实 SMTP。部署及联合实测由主任务继续登记。
