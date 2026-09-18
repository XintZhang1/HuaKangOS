> **0.2补充**：下面的Docker Compose与systemd配置仍是“业务服务”部署示例，不会自动运行维护Worker。完整本机自动改码需要通过start脚本/maintenance.supervisor启动，并按MAINTENANCE.md单独接线。不要直接在业务容器里挂载宿主机Docker socket来启用自动维护。当前自动发布只实现单主机SQLite，不支持PostgreSQL自动备份/迁移与多实例发布。服务器接线、HTTPS、服务账户与部署身份需要单独验收。
>
> 多门店共用一个数据库和一套中心服务，不使用各店本地SQLite的跨网自动同步。原始可信控制器目录、active.json记录的批准版本目录、私密.env与最新一致性数据库备份都要纳入迁移计划。

# 本地 → 服务器：部署与迁移

本文件是实施方案和配置模板，不是已经执行过的服务器部署记录。第一次正式上线应在测试服务器完整演练；不要直接把本地演示数据库上传为生产数据。

## A. 先明确你搬迁的内容

源码、固定版本依赖、数据库、一份私密环境配置及备份恢复说明共同构成应用。只复制源码不能带走业务记录；只复制数据库不能带走 DeepSeek 密钥和启动配置。`.env` 不应进入代码仓库或公开压缩包。

本版最省改动的路径是：一台服务器 + 一个应用进程 + SQLite 持久化目录 + HTTPS 反向代理。是否需要 PostgreSQL 取决于试运行规模和并发实测，而不是“上服务器就必须换数据库”。本地监听 127.0.0.1 只供本机使用，并未替你配置门店局域网多机访问。

## B. SQLite 一致性备份

在项目根目录、相同虚拟环境下运行：

```bash
python -m app.cli backup
# 或自行指定一个尚不存在的目标文件
python -m app.cli backup --output backups/pre-migration.sqlite
```

备份命令可以在应用运行时使用数据库备份接口；目标已存在则拒绝覆盖。输出文件带完整性检查，但没有自动加密或异地复制。需要对操作系统文件权限、磁盘加密、备份介质和保留策略另行管理。

不要将运行中的 `dealer.db` 随手复制并认为一定得到一致数据库。WAL 模式下还有 `-wal`、`-shm` 辅助文件；使用上面的备份接口。

### 恢复演练

1. 停止应用及其他可能写库的进程。保留旧数据库及其关联 WAL/SHM 到私密归档目录，切勿删除唯一副本。
2. 以新的空目录/文件名恢复完整备份，例如 `data/restored.sqlite`，避免混用旧文件的 WAL/SHM。
3. 将 `.env` 的 `DATABASE_URL` 指向恢复文件，执行 `python -m app.cli migrate`。
4. 启动后核对账号、各模块条数、几张已知单据、VIN 关联、近几日日报和汇总。只验证“能登录”不等于恢复成功。
5. 恢复完成后检查旧会话是否应撤销。完整 SQLite 备份包含会话表；可由管理员重置相关账号密码来撤销会话。数据转移脚本则默认不复制登录会话。

## C. Linux 原生服务 + HTTPS

安装支持版本的 Python，在非 root 的独立服务用户目录部署。创建虚拟环境并安装 `requirements.txt`，把真实数据库恢复到权限受限目录，私密写入 `.env`。

示例生产配置：

```dotenv
APP_ENV=production
COOKIE_SECURE=true
ALLOWED_HOSTS=dealer.your-domain.example,127.0.0.1,localhost
DATABASE_URL=sqlite:////srv/dealerdesk/data/dealer.db
APP_TIMEZONE=Asia/Shanghai
ALLOW_AI_EXTERNAL=false
```

不要原样保留示例域名。保留 loopback Host 是为本机健康检查；不要使用 `*`。把 `.env` 和数据目录限制为服务用户/授权管理员访问，确认磁盘持久化和容量监控。

`python -m app.cli migrate` 只迁移结构，不创建新的管理员；新库使用 `init` 交互创建。不要在恢复正式数据库后再调用 `--demo`。

参考 `scripts/dealer.service.example` 配置 systemd，按实际用户名和路径修改。参考 `scripts/Caddyfile.example` 配置域名和反向代理。原生示例的后端只监听 127.0.0.1:8000，公网只开放反向代理的 HTTPS 端口；数据库不要开放公网。

反向代理必须保留 Host 并正确传递 HTTPS 协议信息。本版写接口检查 Origin 与后端识别的外部地址一致；代理信任范围应仅限实际受信任代理。不要为了“消除报错”移除 CSRF 或同源检查。

上线前检查证书、DNS、Cookie 的 Secure 属性、员工权限、账号强密码、备份恢复、日志权限和 AI 外发范围。当前没有独立安全测评、等保或会计口径验收承诺。

## D. Docker 本地/测试示例

安装 Docker 和 Compose 后，在项目根目录：

```bash
cp .env.example .env
# 第一次且需要虚构样例时使用 --demo；正式空库省略它
docker compose run --rm app python -m app.cli init --demo
docker compose up -d
```

本示例将宿主机端口绑定到 `127.0.0.1:8000`，不会自动暴露公网。数据库和备份使用命名卷，不在容器临时层。**不要执行 `docker compose down -v` 删除包含真实业务的卷。**

```bash
docker compose exec app python -m app.cli backup
docker compose logs --tail=100 app
docker compose stop
```

备份仍在容器挂载的备份卷中，需要另行复制到安全位置。不要把“容器中有一个备份”当作异地备份。

此 Docker 配置尚未在本次环境中构建验证。它是本地测试示例，不是完整 HTTPS 生产编排。若反向代理在宿主机、容器或外部负载均衡器，后端所见代理地址可能不是 127.0.0.1，必须据实际网络设定可信代理 IP，并验证 Origin/HTTPS 处理；不能把 `FORWARDED_ALLOW_IPS=*` 当作默认修复。

## E. SQLite → PostgreSQL

源码提供兼容模型和 `scripts/migrate_database.py`，但**本次只实测了 SQLite → SQLite 的完整迁移，尚未实测 PostgreSQL**。正式使用前先对一份备份在测试库演练，并验证全部约束、序列和汇总。

```bash
python -m pip install -r requirements-postgres.txt
```

数据库连接 URL 形式：

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

密码中的特殊字符需正确 URL 编码；生产连接加密按数据库部署要求配置。不要在聊天或共享日志中贴出完整凭据。

迁移顺序：停止原服务写入 → 完成一致性备份 → 建立独立空目标库 → 通过私密环境变量设置 `TARGET_DATABASE_URL` → 运行以下脚本并确认：

```bash
python scripts/migrate_database.py --source sqlite:///./data/dealer.db --target-env TARGET_DATABASE_URL
```

目标必须为空，不会合并或覆盖已有业务。脚本保留主键、业务关联、用户密码哈希、审计、复核、日报和演示标记；不复制登录会话、登录失败记录和任务租约。行数逐表核对；PostgreSQL 的整数主键序列进行重置。目标写入采用事务，结构迁移单独执行，失败后仍应人工确认目标状态。

核对源/目标条数、金额、VIN 占用、审批状态、用户角色及日报后，再更新 `.env` 的 `DATABASE_URL`，启动目标服务，保持源服务停写。确认观察期通过之前保留源备份，不要让两套服务同时接受真实录入形成双主。

PostgreSQL 备份不使用本版 `app.cli backup`；应设置数据库自身备份与恢复演练。当前 Dockerfile 没有安装可选 PostgreSQL 驱动，使用 PostgreSQL 时需相应调整镜像依赖。

## F. 升级

升级前备份 → 停止服务 → 替换源码但保留私密配置与数据 → 安装固定版本依赖 → `python -m app.cli migrate` → 启动并检查。不要用 `Base.metadata.create_all()` 替代版本迁移。未验收的迁移不要直接应用于唯一的生产库。

## G. 常见启动问题

- 未安装 Python / 找不到命令：安装 Python 3.11–3.13，并确认当前终端识别到对应解释器。已有 `.venv` 版本不匹配时，先备份数据，仅重建虚拟环境，不删除 `data`。
- `-Demo` 提示已有用户：这是防止样例混入已有库；后续启动不带 Demo。新演示需要另建空数据库。
- 8000 端口占用：查明占用的程序，不要盲目结束不相关进程。可手工以另一个端口运行 Uvicorn，并用同一地址访问。
- 生产模式无法通过普通 HTTP 登录：Secure Cookie 与 HTTPS 配置是刻意的。建立 HTTPS，不要在正式公网改回不安全 Cookie。
- AI 未配置/失败：先确认本地规则日报可用；在本机检查密钥、开关和模型名，重启后重试。错误信息不会回传 API 密钥或供应商完整响应。
- 关机后没有日报：应用进程未运行。保持服务/服务器运行；补跑窗口默认 7 天，不是无限期自动回补。
