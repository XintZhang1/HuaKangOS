# HuaKangOS / DealerDesk 双机部署手册（阿里云控制器 + 新加坡构建机）

> 本目录只放**部署资产**，不改任何业务代码。文中出现的环境变量名、动词名、路径与行为，
> 全部取自当前代码：`maintenance/config.py`、`maintenance/builder/__main__.py`、
> `maintenance/builder/verbs.py`、`maintenance/builder/lock.py`、`maintenance/transport.py`、
> `maintenance/images.py`、`maintenance/sandbox.py`、`maintenance/window.py`、
> `maintenance/deploy/container.py`、`maintenance/deploy/runtime.py`、`maintenance/supervisor.py`、
> `maintenance/worker.py`、`maintenance/doctor.py`、`app/config.py`、`app/cli.py`、
> `docs/MAINTENANCE.md`、`scripts/dealer.service.example`。
> 脚本本身不会替你填密钥、不会 docker pull、不会 enable/start 服务。

---

## 0. 两台机器、两个角色

| | 阿里云 ECS「控制器主机」 | 新加坡 Vultr「构建机」 |
|---|---|---|
| 地址 | `8.133.192.159`（cn-shanghai） | `207.148.126.193`（主机名 `binance-bot`） |
| 规格 | Ubuntu 22.04，2 vCPU / 1.6 GB，系统 Python 3.10 | Ubuntu 22.04，1 vCPU / 2 GB，系统时区 `Etc/UTC` |
| 跑什么 | ① systemd 服务 `huakangos-controller.service` → `python -m maintenance.supervisor`（受信任控制器）② 业务后端容器 `huakangos-app`（镜像由构建机传来） | ① 受限制的 SSH 强制命令入口 `hk_builder` → `python -m maintenance.builder` ② Docker 构建与隔离测试 ③ **与本项目无关的生产量化/加密交易服务（绝不触碰）** |
| 不跑什么 | 不跑构建、不跑隔离测试、不 docker pull | 不跑业务后端、不存业务数据库、不存业务密钥 |
| 到 Docker Hub | **不通**（所以只走 apt 镜像安装 docker；应用镜像靠 ssh 传输） | 需要能访问 Docker Hub（构建 `python:3.12-slim` 基础镜像）与 GitHub |

数据流：

```
        飞书卡片（人工批准 / 回滚）
                 │
                 ▼
 [阿里云] maintenance.supervisor ──── ssh 强制命令（7 个动词白名单）────▶ [新加坡] maintenance.builder
      │  docker stop/run + /api/health 校验                                   │ git clone/fetch/commit/push
      │  SQLite 一致性备份                                                    │ docker build（候选镜像）
      ▼                                                                      │ docker run 隔离测试（无网络）
 业务容器 huakangos-app  ◀──── docker save | gzip -1 ──── ssh stdout ──── docker load ─┘
 （--user 10001:10001，只发布 127.0.0.1:8000）
```

网络方向：**只有阿里云 → 新加坡的 22 端口出向连接**（`ssh -i KEY -o BatchMode=yes -o StrictHostKeyChecking=yes`，
见 `BuilderClient.argv`）。业务端口只发布在阿里云本机回环，公网入口由宿主机反向代理负责。

---

## 1. 信任边界（动手前必须读）

### 1.1 代码分三类

1. **受信任控制器**（人工审阅、固定在 `/opt/huakangos/controller` 的检出）：`maintenance.supervisor`
   与 `maintenance.worker`，它持有飞书审批凭据、DeepSeek 编码密钥、构建机私钥，并直接管理业务容器。
2. **受信任构建机入口**（同样来自人工审阅的固定检出 `/opt/huakangos-builder/src`）：
   `maintenance.builder` 只接受 7 个动词 `status / context / candidate / image / publish / revert / prune`。
3. **不可信的 AI 候选代码**：只可能出现在构建机专用克隆的临时导出目录里，并且**只在容器中执行**。

### 1.2 代码里能看到的保证（部署依赖这些事实）

* `maintenance/builder/__main__.py`：`$SSH_ORIGINAL_COMMAND` 由 Python `shlex` 解析，只对固定动词白名单分发；
  参数是 `base64(JSON)` 不透明令牌；**任何一边都没有把动词交给 shell**。退出码：`0` 正常（含礼貌拒绝）、
  `1` 拒绝/失败、`3` 内部错误。
* `maintenance/builder/verbs.py`：候选在**写盘的那台机器上**用同一套 `maintenance/policy.py` 重新校验，
  **不信任控制器的结论**；变更文件必须 ⊆ `EDITABLE = {web/app.js, web/style.css, web/index.html, docs/USER_GUIDE.md}`；
  候选必须是基线之上的单一提交。除 `status` 外所有动词都要过维护窗口 + 量化让行 + 构建锁（`state/build.lock`）。
* `maintenance/sandbox.py`：隔离测试容器 `--network none --read-only --cap-drop=ALL
  --security-opt=no-new-privileges --user 65534:65534 --pids-limit 256 --memory 1g
  --cpus min(2, 宿主机 CPU 数)`，
  只读挂载导出的候选源码，**没有数据库、`.env`、Git 元数据、宿主机凭据、docker socket**；
  用的是受信任镜像的 ENTRYPOINT，不是候选仓库里的命令。
* `maintenance/images.py`：受信任测试镜像带标签 `dealerdesk.trusted.sha`，
  与 `HKB_TRUSTED_SHA` 不一致就**拒绝用它测试候选**；候选镜像构建用 `--pull=false`。
* `maintenance/deploy/container.py`：业务容器 `--user 10001:10001 --cap-drop ALL --read-only
  --security-opt no-new-privileges --pids-limit 256 --memory/--cpus 限额`，只发布到 `MAINT_APP_PUBLISH_HOST`
  （默认 `127.0.0.1`）；`--restart=no` —— 生命周期**只属于控制器**，别的进程不许把它拉起来。
  传给容器的环境变量是**白名单** `APP_ENV_KEYS`：`FEISHU_*`、`DEEPSEEK_CODE_*`、`MAINT_REPO_*`、`MAINT_SG_*`
  永远不会进入业务进程。
* `maintenance/transport.py`：镜像以 `docker save | gzip -1` → ssh stdout → 本机 `docker load` 流式传输，
  阿里云磁盘上不留镜像 tar。
* 切换期间的一致性：`switching.lock`（容器内 `/maint/switching.lock`，见 `app/main.py` 的 HTTP 中间件）
  会让业务 API 暂时返回 503；发布顺序是「停旧 → 一致性备份 SQLite → 起新 → `/api/health` 校验
  `release == 候选SHA` → 才快进 Git 主分支」。

### 1.3 这套设计不防什么（别误判）

* **不防宿主机 root**，也不防能登控制器、能读 `/etc/huakangos/huakangos.env`、能改
  `/opt/huakangos/controller` 的人。控制器用户必须在 `docker` 组，而 **docker 组等价于 root**
  （可挂载宿主机任意目录）——这是本设计**明确接受的取舍**，见 `deploy/aliyun/huakangos-controller.service` 注释。
* 不防能直接改专用仓库、能改飞书应用或能批准卡片的内部人员（`docs/MAINTENANCE.md` 已说明：
  `risk=low` 不是安全证明，测试通过也不等于界面没有业务缺陷）。
* 构建机上的 `hkbuild` 同样等价于那台机器的 root（docker 组）；所以那台机器上**不能放**与本项目无关的生产密钥，
  更不能把量化服务的凭据交给它。构建机上的生产量化服务必须靠 `HKB_WINDOW_BANS` 与 `HKB_QUANT_UNITS` 让行。
* 阿里云控制器用户 `huakang` 的 **UID 固定为 10001**，与容器内 `CONTAINER_UID='10001:10001'` 对齐：
  控制器与容器共用一个 SQLite 文件（WAL 模式，`app.cli init` 会设置），只有 UID 相同，双方创建的
  `dealer.db` / `-wal` / `-shm` 才能互相读写。这是 `deploy/aliyun/install.sh` 强制的，不要改成别的 UID。

---

## 2. 本目录文件清单

| 文件 | 作用 | 是否可执行 |
|---|---|---|
| `deploy/README.md` | 本手册 | — |
| `deploy/aliyun/huakangos-controller.service` | 控制器 systemd 单元（跑 `maintenance.supervisor`，不是 uvicorn） | 单元文件 |
| `deploy/aliyun/install.sh` | 阿里云主机初始化（幂等，root 运行） | 是 |
| `deploy/sg/hk_builder` | 构建机 SSH 强制命令包装器（POSIX sh） | 是（安装为 0755 root:root） |
| `deploy/sg/authorized_keys.snippet` | 追加到 `hkbuild:~/.ssh/authorized_keys` 的两行 | — |
| `deploy/sg/install.sh` | 构建机初始化（幂等，root 运行） | 是 |

两台机器都不需要把 `deploy/` 留在生产路径里；脚本把需要的东西安装到 `/opt`、`/etc` 之后即可删除上传目录。

---

## 3. 上线顺序

顺序不能颠倒：**先构建机、后控制器**（控制器启动时会立刻 ssh 构建机确认远程主分支与测试镜像）。

### 3.0 准备（在你自己的电脑上完成）

1. 一个**专用私有仓库**（不要复用量化项目）：把当前 0.2 完整代码提交到 `main`，
   不要提交 `.env`、`data/`、`backups/`、`.venv/`、任何证书或数据库。
2. 飞书**企业自建应用**：开启机器人能力，权限 `im:message:send_as_bot`，
   卡片回调 `card.action.trigger` 用长连接（SDK）方式；准备好审批人的 `open_id`（`ou_` 开头）。
3. DeepSeek API Key（控制器用；`DEEPSEEK_CODE_API_KEY` 可留空以复用 `DEEPSEEK_API_KEY`）。
4. 一个域名 + 反向代理（HTTPS）。`APP_ENV=production` 要求 `COOKIE_SECURE=true`，
   所以**必须有 TLS**；参考 `scripts/Caddyfile.example` 与 `docs/DEPLOYMENT.md` 的 C 节。
5. 记录下「可信基线提交」：`git log -1 --format=%H`（后面要填 `HKB_TRUSTED_SHA`）。

### 3.1 构建机（新加坡）第一遍：建用户/目录/venv/配置模板

```bash
# 在你本机
scp -r deploy/sg root@207.148.126.193:/root/deploy-sg
ssh root@207.148.126.193 'bash /root/deploy-sg/install.sh'
```

这一遍会：安装 `docker.io/git/python3-venv/ca-certificates`、建用户 `hkbuild`
（家目录 `/opt/huakangos-builder`，加入 `docker` 组）、建 `{repository,state,bin,src,.ssh}` 与 venv
（只装 `pydantic==2.13.4`、`python-dotenv==1.2.2`）、安装 `hk_builder` 到
`/opt/huakangos-builder/bin/hk_builder`（root:root 0755）、生成 `/etc/huakangos-builder.env`（hkbuild 0600）、
把 GitHub 公布的 SSH 主机密钥写进 `hkbuild` 的 `known_hosts`。

**它不会做的事**：不动 ufw/iptables、不改全局代理与 `/etc/environment`、不重启任何既有服务
（docker 已在运行就保持原状）、不覆盖已存在的 env 文件、不生成任何密钥。

最后会因为 `HKB_TRUSTED_SHA` 为空而**以非零码退出**——这是刻意的，请继续第 3.2 步。

### 3.2 构建机第二遍：deploy key + 可信基线 + 受信任测试镜像

```bash
# 1) 生成构建机自己的 git deploy key（私钥只留在这台机器）
sudo -u hkbuild -H ssh-keygen -t ed25519 -a 100 -N '' \
  -C 'huakangos-builder@binance-bot' \
  -f /opt/huakangos-builder/.ssh/github_deploy_ed25519
cat /opt/huakangos-builder/.ssh/github_deploy_ed25519.pub     # 登记为仓库 Deploy Key，勾选允许写入

# 2) 填配置（只改这几个；其余保持默认）
vi /etc/huakangos-builder.env
#   HKB_REPO_URL=git@github.com:YOUR_ACCOUNT/dealerdesk.git   （或 https:// 无凭据地址）
#   HKB_REPO_WEB_URL=https://github.com/YOUR_ACCOUNT/dealerdesk
#   HKB_TRUSTED_SHA=<第 3.0 步记录的 40 位提交号>
#   HKB_QUANT_UNITS=<本机生产量化服务的 systemd 单元名，逗号分隔；先用
#                    systemctl list-units --type=service --state=running 看清楚>

# 3) 再跑一遍：克隆可信检出到 src/ 并构建一次受信任测试镜像
bash /root/deploy-sg/install.sh
```

`install.sh` 会 `git checkout --detach --force <HKB_TRUSTED_SHA>` 到 `/opt/huakangos-builder/src`，
然后执行（工作目录就是该检出）：

```bash
docker build -f maintenance/Dockerfile.test --label dealerdesk.trusted.sha="$HKB_TRUSTED_SHA" \
  -t dealerdesk-tests:0.2 .
```

镜像标签与 `HKB_TRUSTED_SHA` 不一致时脚本会拒绝继续；标签一致的镜像会被跳过（**只构建一次**）。
**永远不要用 AI 候选重建这个镜像**：`maintenance/images.py` 的 `trusted_test_image()` 会在每次候选测试前
重新比对标签，标签不符就直接拒绝测试。

### 3.3 构建机：只授权阿里云控制器这一把钥匙

把 `deploy/sg/authorized_keys.snippet` 里 (a) 那一条（`restrict,command="/opt/huakangos-builder/bin/hk_builder"`）
追加到 `/opt/huakangos-builder/.ssh/authorized_keys`，内容必须是**阿里云控制器的公钥**（第 3.6 步生成）：

```bash
chown -R hkbuild:hkbuild /opt/huakangos-builder/.ssh
chmod 700 /opt/huakangos-builder/.ssh
chmod 600 /opt/huakangos-builder/.ssh/authorized_keys
```

`restrict` 关掉 pty、端口转发、agent 转发、X11、sftp；`command=` 让客户端请求变成执行 `hk_builder`。
`hk_builder` 以 `hkbuild` 身份运行，自己从 `/etc/huakangos-builder.env` 读取 `HKB_*`，
切换到 `/opt/huakangos-builder/src` 并 `exec` venv 的 `python -m maintenance.builder`。

### 3.4 阿里云：放代码 + 跑 install.sh

```bash
# 在你本机：把人工审阅过的完整代码放到控制器目录（不要带 .venv/data/.git 之外的私密文件）
rsync -a --exclude .venv --exclude data --exclude .git --exclude backups \
  ./ root@8.133.192.159:/opt/huakangos/controller/
scp -r deploy/aliyun root@8.133.192.159:/root/deploy-aliyun
ssh root@8.133.192.159 'bash /root/deploy-aliyun/install.sh'
```

这一遍会：从 apt 装 `docker.io/python3-venv/python3-pip/git/openssh-client`（**从不 docker pull**）、
建用户 `huakang`（UID 10001、无登录 shell、加入 `docker` 组）、建
`/opt/huakangos/{controller,controller/data,data,data/maintenance,.ssh}` 与 `/etc/huakangos`、
预建 `0660` 的 `data/dealer.db`、生成 `/etc/huakangos/huakangos.env`（root:容器组 0640 的**空值模板**）、
建 venv 并安装 `requirements-maintenance.txt`、安装 systemd 单元并 `daemon-reload`。
它**不** enable/start 服务，也不写任何密钥。

**Python 版本**：`start.ps1` 会断言 3.11–3.13，但这只是 Windows 启动器的保守检查。实测
（2026-09-19，阿里云 8.133.192.159，Python 3.10.12）本项目的固定版本依赖可以全部安装并导入，
代码也没有 3.11+ 专属语法，因此控制器直接跑在系统 Python 3.10 即可。脚本优先选 3.13/3.12/3.11，
都没有才用 3.10，并以脚本末尾的**导入自检**作为真正的判据；依赖装不上或自检失败才以非零码退出。
若确实想装 Python 3.12：

```bash
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get install -y python3.12 python3.12-venv
bash /root/deploy-aliyun/install.sh      # 脚本会自动优先使用 python3.12 重建 venv
```

### 3.5 阿里云：填 `/etc/huakangos/huakangos.env`

必须填的项（模板里有分组注释）：

| 变量 | 说明 |
|---|---|
| `ALLOWED_HOSTS` | 业务域名 + `127.0.0.1`（**健康检查走回环**，`scripts/Caddyfile.example` 已注明）；不能含 `*` 或 `testserver` |
| `DEEPSEEK_API_KEY` | 业务 AI；不用就把 `ALLOW_AI_EXTERNAL` 保持 `false` |
| `MAINT_REPO_WEB_URL` | https 仓库页面（compare 链接） |
| `MAINT_SG_HOST` / `MAINT_SG_USER` / `MAINT_SG_PORT` | 构建机地址与受限用户（本手册用 `hkbuild`；注意 `MaintenanceConfig` 里 `MAINT_SG_USER` 的默认值是 `huakang`，**必须显式写成 hkbuild**） |
| `MAINT_SG_KEY` | 控制器私钥路径（第 3.6 步生成，仅路径，不是密钥内容） |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_APPROVER_OPEN_IDS` / `FEISHU_RECEIVE_ID` | 飞书自建应用与审批人 |
| `MAINTENANCE_ENABLED` / `ALLOW_CODE_EXTERNAL` | 两个都为 `true` 才会外发白名单源码与意见正文 |

改完记得：`chown root:<容器组> /etc/huakangos/huakangos.env && chmod 0640 /etc/huakangos/huakangos.env`
（容器组就是 `install.sh` 打印的 `${CONTAINER_GROUP}`）。`DATABASE_URL`、
`MAINT_RUNTIME_DIR=/opt/huakangos/data/maintenance`、`MAINT_APP_DATA_DIR=/opt/huakangos/data`、
`MAINT_DEPLOY_TARGET=docker-split` 等已由模板填好，除非你改过路径，否则不要动。

### 3.6 阿里云：控制器密钥 + 构建机主机密钥

```bash
sudo -u huakang -H ssh-keygen -t ed25519 -a 100 -N '' \
  -C 'huakangos-controller@8.133.192.159' \
  -f /opt/huakangos/.ssh/sg_builder_ed25519
cat /opt/huakangos/.ssh/sg_builder_ed25519.pub     # → 第 3.3 步的 authorized_keys

# 构建机 install.sh 会打印 /etc/ssh/ssh_host_ed25519_key.pub 的内容与指纹。
# 人工核对指纹后，在阿里云上把「IP + 类型 + 公钥（不要注释）」追加进去：
printf '%s %s %s\n' '207.148.126.193' 'ssh-ed25519' 'AAAAC3NzaC1lZDI1NTE5AAAA...' \
  >> /opt/huakangos/.ssh/known_hosts
chmod 600 /opt/huakangos/.ssh/known_hosts
chown huakang:容器组 /opt/huakangos/.ssh/known_hosts
```

验证这条受限通道（`status` 是唯一不受窗口限制的动词）：

```bash
sudo -u huakang -H ssh -i /opt/huakangos/.ssh/sg_builder_ed25519 \
  -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes \
  hkbuild@207.148.126.193 status
```

返回的 JSON 里应能看到 `"ok": true`、`docker` 版本、`test_image.usable: true`、
`trusted_label` 等于 `HKB_TRUSTED_SHA`、`main_sha` 与远程主分支一致。

### 3.7 阿里云：初始化业务数据库（必须用 `huakang` 身份）

```bash
sudo -u huakang env -i HOME=/opt/huakangos PATH=/usr/bin:/bin \
  bash -c 'set -a; . /etc/huakangos/huakangos.env; set +a; \
           cd /opt/huakangos/controller && .venv/bin/python -m app.cli init'
```

`app.cli init` 会跑 Alembic 迁移、把 SQLite 设为 WAL、创建默认门店与第一个管理员。
想避免交互式输入密码，可以先在同一个环境里导出 `DEALER_INITIAL_PASSWORD`（`app/cli.py` 支持）。
**不要用 root 跑**，否则 `dealer.db` 属主变成 root，控制器与容器都写不进去。

### 3.8 阿里云：自检（不调用 DeepSeek、不发卡片、不发布）

```bash
sudo -u huakang bash -c 'set -a; . /etc/huakangos/huakangos.env; set +a; \
  cd /opt/huakangos/controller && .venv/bin/python -m maintenance.doctor'
# 想验证飞书发送通道（会真的发一条没有按钮的测试卡片）：
#   ... -m maintenance.doctor --send-test
```

`doctor` 在 `docker-split` 模式会打印构建机的 docker 版本、磁盘余量、维护窗口、量化让行状态、
测试镜像标签，并核对本机 `data/maintenance/active.json` 里的运行版本与远程主分支。首次运行
`active.json` 还不存在，它会提示「尚未绑定（首次发布时会绑定到 …）」——这是正常的。

### 3.9 阿里云：启动控制器与反向代理

```bash
systemctl enable --now huakangos-controller
journalctl -u huakangos-controller -f
```

控制器启动后会：确认远程主分支 → 把镜像从构建机流式 `docker load` 到本机（首次会慢，取决于带宽）→
`docker run` 业务容器 → 轮询 `http://127.0.0.1:8000/api/health` 直到 `release` 等于该提交。
反向代理指向 `127.0.0.1:8000` 并终止 TLS（`APP_ENV=production` + `COOKIE_SECURE=true`）。

### 3.10 首轮验收（务必用演示库做一遍）

按 `docs/MAINTENANCE.md` 的建议，用「只改一处文案或样式」的意见跑通三条路径：
批准发布、拒绝、回滚；确认卡片按钮与 Git diff 一致，确认 `PAUSED` 没有出现。
验收完成后才把 `MAINTENANCE_ENABLED` / `ALLOW_CODE_EXTERNAL` 保持为 `true` 用于真实经营。

---

## 4. 日常运行

### 4.1 一次发布的完整链路（对应代码）

1. 员工提交意见并勾选外发授权（或管理员点「授权AI处理」）→ 业务容器写库。
2. 控制器里的 `maintenance.worker`（由 supervisor 拉起；进程若退出，最快 60 秒后自动重启）按预算取任务：
   `remote.context(base_sha)` 只取回白名单文件正文（`web/app.js`、`web/style.css`、`web/index.html`、
   `docs/USER_GUIDE.md`）与固定说明。
3. DeepSeek 返回补丁（最多 12 处精确替换、总规模 ≤500 行）。
4. `remote.candidate(job_id, base_sha, branch, proposal)`：构建机用同一套策略重新校验 → 提交到
   `dealerdesk/change-<编号>-<次数>` → 导出 → 隔离测试 → 通过才 `docker build` 候选镜像并推送候选分支。
5. 飞书卡片显示基线、候选 SHA、改动摘要、文件清单、测试结果与 `compare/BASE...HEAD` 链接。
   白名单前端改动且 `MAINT_AUTO_PUBLISH=true` 时按机械规则自动批准（`AUTO_APPROVER='auto:frontend'`），
   否则等人工点击。
6. 批准 → 控制器 `deploy()`：写 `switching.lock`（业务 API 503）→ 停容器 → SQLite 一致性备份
   （`data/maintenance/backups/pre-<任务>-<sha12>.sqlite`，带 `PRAGMA integrity_check`）→ 起新镜像 →
   `/api/health` 校验 → `remote.publish(base, head, branch)` 普通快进主分支 → 写 `active.json` → 恢复访问。
7. 回滚 → `remote.revert(base, head, job_id)`：先起旧镜像并通过健康检查，再推 Git revert 提交
   （树必须与旧版本完全一致）。

### 4.2 维护窗口与量化让行

* 窗口定义在 `Asia/Shanghai`，默认 `22:00-06:00`，与本机/构建机的系统时区无关（`maintenance/window.py`
  显式换算，构建机是 `Etc/UTC` 也不会错位）。
* `HKB_WINDOW_BANS=23:50-00:30,03:50-04:30`（构建机；`MAINT_WINDOW_BANS` 同理）是量化任务保护区间，
  默认值对应 00:01 / 04:01 的 trader 触发。
* 时间闸门之外还有状态闸门：`quant_state()` 用 `systemctl is-active <单元>` 检查 `HKB_QUANT_UNITS` /
  `MAINT_QUANT_UNITS` 里的单元。**如果这些单元在跑，本次构建/发布直接让行**（返回 `not_now`，属于正常结果，
  任务留在队列里下次再试）。`HKB_QUANT_UNITS` 留空 = 不检查，只靠时间窗口——请务必按 3.2 步填上
  构建机上真实的生产单元名。
* 剩余时间不足 `HKB_MIN_SEGMENT_MINUTES`（默认 20 分钟）时也不会开新构建。

### 4.3 预算、有效期与自动发布

* `MAINT_MAX_JOBS_PER_DAY`（默认 3）是**每个 UTC 自然日的模型请求次数**上限，不是金额上限。
* `MAINT_APPROVAL_HOURS`（默认 24）是审批有效期；过期卡片不能发布。
* `MAINT_AUTO_PUBLISH=true` 只对 `change_tier()==auto`（改动文件 ⊆ 白名单）生效；发布前还会机械复核一次。
* 回滚按钮只对**当前最新部署**有效，默认 24 小时内可用。

### 4.4 状态、日志、备份、磁盘

| 想看什么 | 去哪里看 |
|---|---|
| 控制器日志 | `journalctl -u huakangos-controller -f` |
| 控制器状态文件 | `/opt/huakangos/data/maintenance/{status.json,active.json,PAUSED}` |
| 界面里的维护状态 | 管理员调 `GET /api/maintenance/status`（读 `/maint/status.json`） |
| 业务容器 | `docker ps`、`docker logs huakangos-app`（只读观察；不要手工 restart/rm，生命周期属于控制器） |
| 发布备份 | `/opt/huakangos/data/maintenance/backups/*.sqlite` |
| 构建机审计 | `/opt/huakangos-builder/state/audit.log`（每个动词一行 JSON）、`state/crash.log` |
| 构建机磁盘 | `ssh ... status` 里的 `disk_free_gb`；低于 `HKB_MIN_FREE_GB`（默认 3GB）会拒绝新候选 |
| 清理镜像 | 候选流程末尾会在构建机上执行 `prune`（保留最近 3 个应用镜像，从不删测试镜像） |

---

## 5. 故障排查

先跑 `maintenance.doctor`（3.8 步），它会把大部分问题直接打印出来。

| 症状 | 原因与处理 |
|---|---|
| `请明确设置 ALLOW_CODE_EXTERNAL=true；意见与白名单源码才会外发` | 两个开关没同时打开；确认愿意外发白名单源码后再开 |
| `docker-split 模式必须配置 MAINT_SG_HOST` / `MAINT_SG_KEY 必须指向构建机私钥文件` | env 未填或私钥路径不存在/不可读（`Path(sg_key).is_file()` 为假） |
| `构建机不可达或超时（status）；未执行任何发布动作` | 阿里云到 207.148.126.193:22 不通，或 known_hosts 缺该主机、私钥权限不对。先用 3.6 步的 `ssh ... status` 手工验证 |
| `ssh: Host key verification failed` | 控制器用 `StrictHostKeyChecking=yes`，`/opt/huakangos/.ssh/known_hosts` 里没有构建机主机密钥 |
| `Permission denied (publickey)` | `authorized_keys` 内容不是控制器公钥，或权限不对（目录 700、文件 600、属主 hkbuild）；sshd StrictModes 会直接忽略权限不对的条目 |
| `hk_builder: 无法读取 /etc/huakangos-builder.env` | env 文件属主不是 hkbuild（必须 hkbuild:hkbuild 0600），或不存在 |
| `hk_builder: 缺少可信检出目录` / `ModuleNotFoundError: maintenance` | `/opt/huakangos-builder/src` 未检出；重跑 `deploy/sg/install.sh`（它会 checkout `HKB_TRUSTED_SHA`） |
| 构建机返回 `not_now`（窗口关闭 / 量化任务运行 / 剩余时间不足） | **正常让行**，任务留在队列，等下一个维护时段；不需要处理。若长期不执行，检查 `HKB_WINDOW_*` 与 `HKB_QUANT_UNITS` |
| `构建机正忙：已有另一个构建或测试在运行` | 构建锁被占用；上一次构建还在跑（1 vCPU 会慢），稍后重试即可 |
| `隔离测试镜像的基线标签为 …，与 HKB_TRUSTED_SHA 不一致` | 有人在候选/其它提交上重建过测试镜像。用 `deploy/sg/install.sh` 从固定提交重建，**不要**手工 `docker build` 顶替 |
| 隔离测试报 `range of CPUs is from 0.01 to 1.00` | 构建机只有 1 vCPU，而 docker 不接受 `--cpus 2`。当前代码的 `maintenance/sandbox.py::host_cpus()` 已自动夹到宿主机核数；仍报错说明构建机上的 `maintenance/` 不是这份代码（核对 `HKB_TRUSTED_SHA` 与 `/opt/huakangos-builder/src`） |
| 候选测试总是失败且日志显示读不到 `/source` | 导出目录权限被收紧（例如有人给 `hk_builder` 加了 `umask 077`）。测试容器以 `65534:65534` 读取只读挂载，必须保持 `umask 022` |
| 控制器起不来，日志里有 3.10 相关语法/依赖错误 | 解释器版本不受支持；装 `python3.12`+`python3.12-venv` 后重跑 `deploy/aliyun/install.sh` |
| 服务反复重启，日志 `请明确设置…` / `需配置飞书…` | env 没填全；`Restart=always` 会每 5 秒重启，先 `systemctl stop` 再改配置 |
| 容器起来了但 `/api/health` 一直不通过、`release` 为空 | 镜像里没有 `DEALER_RELEASE_SHA`（不该发生，控制器会注入）或数据库不可写：检查 `dealer.db` 属主/权限（应为 `huakang:容器组 0660`）与 `docker logs huakangos-app` |
| SQLite 报 `attempt to write a readonly database` | UID/权限被改动：`huakang` 的 UID 必须是 10001，`data/` 与 `data/maintenance/` 为 `0770 huakang:huakang`，`dealer.db` 为 `0660`。重跑 `deploy/aliyun/install.sh` 可校正 |
| 界面维护状态显示默认文案 | 单元 `UMask=0077` 让 `data/maintenance/*.json` 只有 `huakang` 可读，容器内用户 10001 读不到 `status.json`（只影响界面展示，`switching.lock` 的存在性检查仍生效）。要显示状态可临时用 `systemctl edit` 覆盖 `UMask=0027` |
| 首次发布卡在镜像传输 | 1.6GB/带宽有限时 `docker save → gzip → docker load` 会慢；`MAINT_SG_TIMEOUT` 默认 900 秒，镜像传输用它的 4 倍。不要中断，也不要手工 `docker pull`（本机到 Docker Hub 不通） |
| 改了 `usermod -aG docker` 但控制器仍报 docker 不可用 | 组变更只对新会话生效：`systemctl restart huakangos-controller` |
| 控制器/构建机磁盘满 | 控制器：清理 `data/maintenance/backups`（保留最近的）与旧镜像；构建机：`docker image prune`、关注 `HKB_MIN_FREE_GB` |

---

## 6. 回滚

### 6.1 卡片回滚（支持的路径）

飞书卡片上的「回滚」按钮 → 控制器 `rollback()`：校验该任务确实是**当前运行的最新版本**且在
`MAINT_APPROVAL_HOURS`（默认 24 小时）内 → `remote.revert(base, head, job_id)` 让构建机创建 Git revert 提交
（要求当前主分支仍等于已发布的 head，且 revert 后的树与原基线完全一致）→ 停当前容器 → 再备份一次数据库 →
启动旧镜像并通过健康检查 → 更新 `active.json` 与任务状态。

**数据库永不回滚**：回滚只回代码，期间新录入的业务记录继续保留。

### 6.2 卡片过期或系统处于 `PAUSED`

`PAUSED` 出现在 `/opt/huakangos/data/maintenance/PAUSED` 时，控制器**不再执行新的发布/回滚**
（业务服务照常运行在已知版本上）。它不是点一下就能清掉的标记：

1. 停控制器：`systemctl stop huakangos-controller`（业务容器也会被停，属于预期）。
2. 核对：`/etc/huakangos/huakangos.env`、`data/maintenance/active.json`（`sha`/`image`）、
   构建机上远程主分支 `sha`（`ssh … status` 的 `main_sha`）、`data/maintenance/backups/` 里的备份、
   `state/audit.log`。
3. 如果只是健康检查失败而 Git 主分支仍等于旧基线：修好原因 → 保留 `PAUSED` 内容作记录（改名为 `PAUSED.bak-<日期>`）
   → 启动控制器。
4. 如果 Git 与运行版本已经不一致、或你无法确认远端状态：**不要**继续自动发布。
   需要回到旧版本时，按 6.3 手动指回旧镜像，并人工在仓库里 revert（或让卡片流程处理）。

### 6.3 手动回到旧镜像（无法用卡片时）

```bash
systemctl stop huakangos-controller
cp /opt/huakangos/data/maintenance/active.json /root/active.json.bak
# 把 sha 与 image 改成上一个已发布版本（image 必须以 :<sha> 结尾，否则 safe_release() 会拒绝加载）
vi /opt/huakangos/data/maintenance/active.json
chown huakang:容器组 /opt/huakangos/data/maintenance/active.json
systemctl start huakangos-controller
journalctl -u huakangos-controller -f     # 观察是否用旧镜像启动并通过健康检查
```

此时控制器会报「已部署版本与远程主分支不一致；请人工核对后再启用」并保持 `ready=false`——
这是刻意的：它不会在 Git 主分支指向新版本时假装一切正常。把 Git 侧也 revert 掉（或让审批流程重新发布）
之后，这个提示才会消失。

### 6.4 完全手工兜底（不推荐）

`docker run` 的参数由 `maintenance/deploy/container.py` 的 `container_run_argv()` 决定；手工仿写容易漏掉
`--read-only`、`--cap-drop ALL`、`--user 10001:10001`、`--restart=no` 这些关键限制，也可能与控制器抢同一个容器名。
只有在控制器完全不可用时才这么做，并保证事后把控制器停掉或恢复成唯一管理者（`--restart=no` 就是为了这个）。

---

## 7. 读代码时发现的差异与坑（照实列出）

1. **`HKB_GIT_SSH_KEY` 在 Python 里没有被消费**：`BuilderConfig` 声明了它，但 `maintenance/gitops.py`
   只设置 `GIT_TERMINAL_PROMPT` / `GIT_LFS_SKIP_SMUDGE`，没有任何代码读取这个变量。
   `deploy/sg/hk_builder` 因此在 shell 层把它翻译成 `GIT_SSH_COMMAND`（只加 `-i` 与 `IdentitiesOnly`），
   否则 git 会去用 `hkbuild` 的默认密钥或 `~/.ssh/config`。
2. **`MAINT_APP_GATE_DIR` 声明但未使用**：容器门禁路径在 `container.py` 里固定为 `/maint/switching.lock`
   （runtime 目录挂载到 `/maint`）。env 模板里没有放这个变量，避免误导。
3. **`MAINT_SG_USER` 的默认值是 `huakang`**，而本部署在构建机上用的是 `hkbuild`：必须显式设置，
   否则 `_validate_split()` 虽然通过，但 ssh 会去连一个不存在的账号。
4. **构建机需要项目源码可导入**：强制命令执行的是 `python -m maintenance.builder`，因此
   `/opt/huakangos-builder/src` 必须是一份固定检出（`install.sh` 负责 checkout `HKB_TRUSTED_SHA`）。
   这个目录**不能**用 `HKB_ROOT/repository`（那是 `Repository.sync()` 自己 `git clone` 的地方，
   AI 候选会在其中提交），否则信任边界会被搅在一起。
5. **测试容器以 `65534:65534` 读取导出的候选树**：`hk_builder` 必须显式 `umask 022`，
   否则导出的源码是 `0600/0700`，隔离测试永远读不到 `/source`。
6. **`huakang` 的 UID 必须是 10001**：与容器内 `CONTAINER_UID='10001:10001'` 对齐，才能共用 WAL 模式的
   `dealer.db`（`-wal`/`-shm` 也要能被对方读写）。这是 `install.sh` 的硬检查。
7. **`data/dealer.db` 的应用级初始化靠 `python -m app.cli init`**（Alembic 迁移 + WAL + 首位管理员）；
   容器启动时如果 `users` 表不存在会直接 `RuntimeError`，所以不能跳过 3.7 步。
8. **`ALLOWED_HOSTS` 必须包含 `127.0.0.1`**：控制器的健康检查请求 `http://127.0.0.1:8000/api/health`，
   `TrustedHostMiddleware` 会校验 Host（`scripts/Caddyfile.example` 也注明了这一点）。
9. **`MAINT_TEST_IMAGE` 在 `docker-split` 模式下不在阿里云生效**：本机 `preflight()` 只检查 docker CLI；
   真正被检查的是构建机的 `HKB_TEST_IMAGE` 与其 `dealerdesk.trusted.sha` 标签。
10. **单元里的 `UMask=0077` 会让 `/maint/status.json` 对容器不可读**（界面状态显示默认文案），
    但 `switching.lock` 的存在性检查（`Path(gate).exists()`）仍然有效，门禁不会失效。
11. **`ProtectSystem=strict` 不会阻止连接 `/run/docker.sock`**（systemd 文档明确说明只读挂载不影响
    AF_UNIX 套接字通信），所以单元里不需要给 docker socket 开 `ReadWritePaths`。
12. **`app/db.py` 在导入时执行 `(ROOT/'data').mkdir(exist_ok=True)`**：单元是只读根文件系统，
    所以 `install.sh` 预先创建 `/opt/huakangos/controller/data`，否则控制器一导入 `app.db` 就崩。

---

## 8. 相关文档

* `docs/MAINTENANCE.md`：自动维护与飞书审批的完整说明、验收边界、PAUSED 的处置。
* `docs/DEPLOYMENT.md`：SQLite 一致性备份与恢复演练、Linux 原生服务 + HTTPS、升级流程。
* `scripts/dealer.service.example`、`scripts/Caddyfile.example`：本手册 systemd 加固姿态与反向代理的参考原型。