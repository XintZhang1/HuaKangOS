# M5.8 编码审阅与实测记录（Linux worker 部署定义和开关回退）

2026-09-28，集中测试阶段。Astra 批次未开始 M5.8；本轮实现 + 静态实测。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 部署定义 | `compose.yml` 新增 `assistant-worker` 服务（显式 profile、同镜像、同 `.env`、同数据卷、`command: python -m app.assistant_worker`、`--health` 健康检查、`stop_grace_period: 90s`、`no-new-privileges` + `cap_drop: ALL`、不暴露端口） |
| 运维文档 | 新增 `docs/assistant-runtime-operations.md`（四开关、同库同版本、备份先行、启动/停止、健康与不健康含义、升级与回退、不降级删表） |
| 未改动 | `Dockerfile`（worker 复用同一镜像与入口覆盖，无需细调）、`start.sh`（Web 入口的初始化行为不变）、`app/*`（本项无产品代码改动） |

关键约束：worker **不执行** `app.cli init`/迁移/建库，不跑日报 Scheduler（compose 内显式
`SCHEDULER_ENABLED=false`、`SCHEDULER_MODE=off`）；默认 profile 下 `docker compose up` 只启动 Web。

## 2. 实测结论（真实运行，未启动任何容器）

运行 `20260928T063142Z-43abd9857f`：`status=passed`，`phase_complete=true`。

- `m58-deployment-definition`：7 passed。
  1. 自带的最小 compose 读取器是 fail-closed 的：制表符缩进、非映射行都被拒绝；
  2. Web 服务保持原入口（无 `command` 覆盖、原端口、原健康检查）；
  3. worker 是独立且需显式 profile 的服务：`profiles=["assistant-worker"]`、命令为
     `python -m app.assistant_worker`、不暴露任何端口、`restart=unless-stopped`、
     `stop_grace_period ≥ 90s`；
  4. worker 命令不含 `cli`/`init`/`migrate`/`start.sh`/`uvicorn`，Scheduler 被显式关闭，
     整份文档不含 redis；
  5. Web 与 worker 的 `build`/`env_file`/`DATABASE_URL`/`volumes`/`security_opt`/`cap_drop` 完全一致
     （同镜像、同库、同安全限制）；
  6. 健康检查命令为 `python -m app.assistant_worker --health`，含 `interval`/`timeout`/`retries`/`start_period`；
  7. 运维文档覆盖四个开关、`--health`、显式 profile 启动、先备份、同一镜像、downgrade 边界，
     且不含 `sk-`/`api_key=`/`password=`/`secret=`/`token=` 等密钥样例。
- `m58-affected-entrypoint-regression`：17 passed（Web 健康入口 + 原本地预览契约未变）。

## 3. 人工审查要点

- 只有显式 `--profile assistant-worker` 才启动 worker；Web 部署行为与本文档之前完全一致。
- worker 与 Web 同库同版本：worker 启动只读校验迁移头，缺 `h53k` 或库不可达即退出码 2。
- 停止语义：SIGTERM 立即停止领取，已领取的 Run 走到自己的安全边界；超过宽限期被强杀时，
  租约到期由下一实例按 CAS 恢复，不重放已确认提交。
- 文档不含密钥样例，也不建议关闭既有安全开关；未新增 Redis 或任何中间件。
- 不改迁移、不降级删表：Runtime downgrade 仅允许在明确标记的空合成库上执行。

## 4. 尚未由运行证据覆盖（属 M8.8）

- 真实 Linux 上的镜像构建、`docker compose --profile assistant-worker up` 启动与停止、
  healthcheck 真实轮询与恢复演练。
- 真实 PostgreSQL 作为同库数据源时的 worker 启动与槽位竞争。
- 两个实例同时运行（Web 嵌入 + 独立 worker）在真实部署下的行为。

源码指纹：`9360f51e72d2d7c864473fb50d2ae65fd9f63a9805a2dce889be2adce3d9f9c2`。
