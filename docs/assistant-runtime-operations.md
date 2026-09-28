# 业务助手 Runtime worker 运维说明

适用对象：已按 `Dockerfile` 构建同一镜像、并使用同一个明确数据库的部署方。
本文只描述**独立 worker 进程**的运行、健康与停止；它不授予任何业务权限，也不改变原业务状态机。

## 1. 四个功能开关（默认全部关闭）

| 开关 | 作用 | 默认 |
|---|---|---|
| `ASSISTANT_HOME_ENABLED` | 助手首页入口 | `false` |
| `ASSISTANT_RUNTIME_ENABLED` | 持久 Run / 队列 / worker 领取执行 | `false` |
| `ASSISTANT_FOLLOWUP_ENABLED` | 每件事的持续跟进（需 Runtime 已开启） | `false` |
| `ASSISTANT_NOTIFICATIONS_ENABLED` | 站内提醒生成与读取 | `false` |

- 开关只从 `.env` 或进程环境读取，`ASSISTANT_FOLLOWUP_ENABLED=true` 而 Runtime 关闭会被配置直接拒绝。
- 关闭 Runtime 时 worker 不领取任何执行，只写自己的基础设施心跳；已有原单、草稿、卡片与
  Runtime 记录一律保留，不做回滚。
- 重新开启后按当前真实授权继续，不自动确认任何业务。

## 2. 与 Web 服务的关系

- **同一镜像、同一 `.env`、同一数据卷**：`DATABASE_URL` 必须与 Web 完全一致，且必须已经升级到
  本镜像的迁移头。worker 启动时只读校验：显式 `DATABASE_URL`、库可达、九张 Runtime 表齐全、
  迁移头包含 `h53k_assistant_runtime`；任一不满足即以退出码 2 拒绝启动。
- worker **不执行** `app.cli init` / 迁移 / 建库，也不跑日报 Scheduler
  （compose 中显式 `SCHEDULER_ENABLED=false`、`SCHEDULER_MODE=off`）。
- 只运行一个数据库槽位：多个 worker 同时运行也不会重复准备同一件事；冲突的会话按原契约等待或拒绝。

## 3. 启动与停止

```bash
# 仅启动 Web（不含 worker）：默认 profile 就只启动 app
docker compose up -d app

# 显式启动独立 worker（先确认 Web 已完成迁移）
docker compose --profile assistant-worker up -d assistant-worker
```

- `SIGTERM`/`docker compose stop`：worker 立即停止领取新执行，并让已领取的 Run 走到自己的安全边界；
  `stop_grace_period: 90s` 覆盖这一收尾。超过宽限期被强杀时，租约到期后由下一次启动的 worker
  按 CAS 恢复（不会重放已确认的业务提交）。
- 重启后不承诺"关闭电脑期间继续运行"：机器休眠或容器停止期间不会执行；恢复后按真实事实重新判断。

## 4. 健康检查

```bash
docker compose --profile assistant-worker exec assistant-worker python -m app.assistant_worker --health
```

输出为只读聚合：运行开关、源码指纹、数据库安全标识、60 秒内的 worker 心跳、队列计数
（queued/running/过期待恢复）、最近完成时间与 `issues` 列表。

- 退出码 `0` 表示健康：Runtime 已开启、至少一个心跳在 60 秒内、没有等待恢复的过期租约。
- 退出码 `1` 表示不健康：`runtime_disabled`（开关关闭）、`worker_heartbeat_stale`（worker 过期，
  Web 可能仍在运行）、`expired_lease_pending`（有过期租约待恢复）、迁移/库检查失败（如
  `runtime_migration_missing`、`database_unreachable`）。
- 输出只有计数、时间、指纹与错误码；不含账号、客户、会话内容、数据库 URL 或任何密钥。
- `--once` 只执行一个周期后退出，便于排障；不要用它替代常驻 worker。

## 5. 升级与回退

1. **先备份**：数据库与私有附件必须联合备份，并在副本上验证可恢复，再升级正式副本。
2. **同库同版本**：升级迁移后先启动 Web 验证，再启动 worker；worker 与 Web 必须来自同一镜像版本。
3. **不加新依赖**：worker 不需要 Redis、消息队列或额外中间件；数据库就是队列。
4. **回退**：不要用迁移 downgrade 删表。Runtime 的 downgrade 只允许在明确标记的空合成库上执行；
   正式实例回退走"停止 worker → 恢复已验证备份 → 用回退版本启动"，历史记录只增不删。
5. 停止服务不等于撤销业务：已确认的原业务事实、草稿、卡片与通知都保留。

## 6. 迁移与账号边界

- 生产环境要求 HTTPS、安全 Cookie、明确 `ALLOWED_HOSTS` 与 `FILE_SCAN_MODE=clamav`；
  旧 legacy 业务写入在生产被配置拒绝。
- worker 不创建员工、不重置密码、不初始化账号；账号与门店权限仍由管理员在原 Web 界面维护。
- 真实 Linux 部署与恢复演练属 M8.8，未完成前不得把本文件当作已验收的部署证明。
