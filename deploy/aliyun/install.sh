#!/usr/bin/env bash
# =============================================================================
# deploy/aliyun/install.sh
# 阿里云 ECS「控制器主机」初始化脚本
#   （8.133.192.159 / cn-shanghai / Ubuntu 22.04 / 2vCPU 1.6GB / 系统 Python 3.10）
#
# 【本脚本做什么】
#   1. 只用 Ubuntu/阿里云 apt 镜像安装 docker.io、python3-venv、python3-pip、git、
#      openssh-client（DEBIAN_FRONTEND=noninteractive）。
#      本机到 Docker Hub 不通，因此**从不 docker pull 任何镜像**：业务镜像由新加坡
#      构建机经 ssh 单向传输（docker save | gzip -1 → docker load，见
#      maintenance/transport.py 的 stream_image_into），测试镜像也只存在于构建机。
#   2. 建专用系统用户 huakang（无登录 shell）并加入 docker 组。
#   3. 建 /opt/huakangos/{controller,controller/data,data,data/maintenance,.ssh} 与
#      /etc/huakangos，设定属主/权限。
#   4. 优先用 3.13/3.12/3.11；都没有就用系统 python3（Ubuntu 22.04 = 3.10，已实测可用）建 venv 并
#      安装 requirements-maintenance.txt；安装失败或解释器版本不受支持时**明确报错并
#      以非零码退出**，提示改用 Python 3.12，绝不静默继续。
#   5. 安装 huakangos-controller.service 到 /etc/systemd/system/ 并 daemon-reload
#      （**不 enable、不 start**，等人工填好环境文件后由人启动）。
#   6. 打印必须人工填写的环境变量清单与后续步骤。
#
# 【本脚本故意不做什么】
#   * 不写任何密钥；/etc/huakangos/huakangos.env 只在缺失时生成一份**空值模板**，
#     已存在时绝不覆盖。
#   * 不克隆代码仓库、不构建任何镜像、不运行 setup-maintenance.sh、不 enable/start 服务。
#   * 不配置反向代理与防火墙，不动业务数据内容，不 docker pull。
#
# 幂等：可以反复执行（不覆盖已存在的 env 文件与 SSH 密钥）。
# =============================================================================
set -euo pipefail

readonly APP_USER='huakang'
readonly CONTAINER_UID='10001'
readonly CONTAINER_GROUP_NAME='huakangos-app'
readonly APP_ROOT='/opt/huakangos'
readonly CONTROLLER_DIR="${APP_ROOT}/controller"
readonly DATA_DIR="${APP_ROOT}/data"
readonly MAINT_DIR="${DATA_DIR}/maintenance"
readonly SSH_DIR="${APP_ROOT}/.ssh"
readonly ENV_DIR='/etc/huakangos'
readonly ENV_FILE="${ENV_DIR}/huakangos.env"
readonly UNIT_NAME='huakangos-controller.service'
readonly UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"
readonly VENV_DIR="${CONTROLLER_DIR}/.venv"

info() { printf '\n\033[1;32m[huakangos]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die '请用 root 运行：sudo bash deploy/aliyun/install.sh'
command -v apt-get >/dev/null 2>&1 || die '本脚本只支持 Debian/Ubuntu（找不到 apt-get）'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly UNIT_SRC="${SCRIPT_DIR}/${UNIT_NAME}"

# -----------------------------------------------------------------------------
# 1. apt 依赖：只走 Ubuntu/阿里云镜像，不从 Docker Hub 拉镜像
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
info '步骤 1/7：从 apt 镜像安装 docker.io / python3-venv / python3-pip / git / openssh-client'
apt-get update || die 'apt-get update 失败：请检查 /etc/apt/sources.list 中的阿里云镜像与本机网络（本脚本不会改用 Docker Hub 或第三方源）'
apt-get install -y --no-install-recommends docker.io python3-venv python3-pip git openssh-client \
  || die 'apt 安装失败：请检查磁盘空间与镜像可达性后重试'

systemctl enable --now docker >/dev/null 2>&1 || warn 'docker 服务启用失败，请手动检查 systemctl status docker'
if ! docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  die 'docker 守护进程不可用：控制器无法创建业务容器。请检查 systemctl status docker 后重试'
fi
info "docker 就绪：$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '未知版本')（本机不拉取任何镜像，业务镜像由构建机传输）"

# -----------------------------------------------------------------------------
# 2. 容器 GID 组 + 控制器用户
#    关键：huakang 的 UID 必须与容器内的 CONTAINER_UID='10001:10001'
#    （maintenance/deploy/container.py）一致。控制器与业务容器共用同一个 SQLite
#    文件（WAL 模式），只有 UID 相同，两边创建的 dealer.db / -wal / -shm 才都能
#    被对方读写；靠组权限补救不了容器以默认 umask 022 创建的文件。
# -----------------------------------------------------------------------------
if getent group "${CONTAINER_UID}" >/dev/null 2>&1; then
  CONTAINER_GROUP="$(getent group "${CONTAINER_UID}" | cut -d: -f1)"
  info "步骤 2/7：宿主机 GID ${CONTAINER_UID} 已被组 ${CONTAINER_GROUP} 占用，直接复用（不新建、不改名）"
else
  CONTAINER_GROUP="${CONTAINER_GROUP_NAME}"
  groupadd --system --gid "${CONTAINER_UID}" "${CONTAINER_GROUP}"
  info "步骤 2/7：已创建组 ${CONTAINER_GROUP}（GID ${CONTAINER_UID}，与容器内用户一致）"
fi
readonly CONTAINER_GROUP

if id -u "${APP_USER}" >/dev/null 2>&1; then
  actual_uid="$(id -u "${APP_USER}")"
  if [[ "${actual_uid}" != "${CONTAINER_UID}" ]]; then
    die "用户 ${APP_USER} 已存在但 UID=${actual_uid}，与容器 UID ${CONTAINER_UID} 不一致。请先人工核对（业务库权限依赖两者相同），本脚本不会擅自改动既有用户。"
  fi
  info "用户 ${APP_USER} 已存在（UID ${actual_uid}），跳过创建"
else
  useradd --system --uid "${CONTAINER_UID}" --gid "${CONTAINER_GROUP}" \
    --create-home --home-dir "${APP_ROOT}" --shell /usr/sbin/nologin \
    --comment 'HuaKangOS controller' "${APP_USER}" \
    || die "创建用户 ${APP_USER} 失败"
  info "已创建系统用户 ${APP_USER}（UID ${CONTAINER_UID}，无登录 shell）"
fi

# docker 组等价于 root：可以挂载宿主机任意目录、进入任意容器。控制器本来就要创建/
# 停止业务容器并挂载业务数据目录，所以这是本设计**明确接受的取舍**。
# 代价：huakang 账号与 /opt/huakangos/controller 里的代码都在信任边界内，
# 那里只能放人工审阅过的控制器代码，绝不放 AI 生成的候选代码。
usermod -aG docker "${APP_USER}"
usermod -aG "${CONTAINER_GROUP}" "${APP_USER}"
info "已把 ${APP_USER} 加入 docker（root 等价，接受的取舍）与 ${CONTAINER_GROUP} 组；改组后需 restart 服务才生效"

# -----------------------------------------------------------------------------
# 3. 目录与权限
# -----------------------------------------------------------------------------
info '步骤 3/7：创建目录与权限'
install -d -m 0750 -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${APP_ROOT}"
install -d -m 0750 -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${CONTROLLER_DIR}"
# controller/data 是 app/db.py 启动时 (ROOT/'data').mkdir(exist_ok=True) 的目标：
# 单元里 ProtectSystem=strict 让它只读，所以必须预先存在，否则控制器导入 app.db 就崩。
install -d -m 0750 -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${CONTROLLER_DIR}/data"
install -d -m 0700 -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${SSH_DIR}"
install -d -m 0750 -o root -g "${CONTAINER_GROUP}" "${ENV_DIR}"
# 业务数据目录：控制器（UID 10001）与容器（10001:10001）是同一个 UID，所以属主权限就够，
# 不需要 setgid；而且单元里的 RestrictSUIDSGID=true 会拒绝 chmod 2770（EPERM）。
install -d -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${DATA_DIR}"
chmod 0770 "${DATA_DIR}"
install -d -o "${APP_USER}" -g "${CONTAINER_GROUP}" "${MAINT_DIR}"
chmod 0770 "${MAINT_DIR}"

# SQLite 库文件：控制器与容器都要写（WAL 模式）。0 字节文件是合法的空库。
DB_FILE="${DATA_DIR}/dealer.db"
if [[ -e "${DB_FILE}" ]]; then
  chown "${APP_USER}:${CONTAINER_GROUP}" "${DB_FILE}"
  chmod 0660 "${DB_FILE}"
  info "已校正现有 ${DB_FILE} 的属主/权限（0660，huakang:${CONTAINER_GROUP}）"
else
  install -m 0660 -o "${APP_USER}" -g "${CONTAINER_GROUP}" /dev/null "${DB_FILE}"
  info "已预建空数据库文件 ${DB_FILE}（0660）：请用 huakang 身份执行 python -m app.cli init 初始化"
fi

# -----------------------------------------------------------------------------
# 4. /etc/huakangos/huakangos.env（只在不存在时写模板，绝不写密钥、绝不覆盖）
# -----------------------------------------------------------------------------
if [[ -e "${ENV_FILE}" ]]; then
  info "步骤 4/7：${ENV_FILE} 已存在，保持不变（本脚本永不覆盖、永不写入密钥）"
else
  cat >"${ENV_FILE}" <<'ENVEOF'
# HuaKangOS / DealerDesk 控制器环境文件（systemd EnvironmentFile 格式）
# 由 deploy/aliyun/install.sh 在文件缺失时生成的**空值模板**；本脚本不会覆盖它，也不会代填密钥。
# 格式：KEY=VALUE，不加引号、值里不留空格、不用 export，可写 # 注释。
# 权限：root:<容器组> 0640。systemd 以 root 读取后再把进程降权到 huakang。
# 不要把本文件内容发到聊天工具，也不要提交进 Git。

# --- 业务容器基础配置（经 maintenance/deploy/container.py 的 APP_ENV_KEYS 白名单进入容器）---
APP_ENV=production
APP_TIMEZONE=Asia/Shanghai
# 必填：业务对外域名/IP，逗号分隔，不能含 * 或 testserver；APP_ENV=production 时校验
ALLOWED_HOSTS=
# APP_ENV=production 时必须为 true：登录 Cookie 只走 HTTPS（反向代理需终止 TLS）
COOKIE_SECURE=true
SESSION_HOURS=8
SCHEDULER_ENABLED=true
DAILY_REPORT_HOUR=0
DAILY_REPORT_MINUTE=15
REPORT_CATCHUP_DAYS=7
API_DOCS_ENABLED=false
PORT=8000
# uvicorn 读取的变量；只信任本机反向代理
FORWARDED_ALLOW_IPS=127.0.0.1

# --- 数据库（控制器与容器共用同一个 SQLite 文件）---
DATABASE_URL=sqlite:////opt/huakangos/data/dealer.db

# --- 业务 AI（可选）---
ALLOW_AI_EXTERNAL=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=60
AI_MAX_RECORDS=400
INVENTORY_AGING_DAYS=90
REPAIR_OVERDUE_DAYS=7
RECEIVABLE_GRACE_DAYS=3
LOW_GROSS_MARGIN_PERCENT=2
LARGE_CASH_AMOUNT_YUAN=50000
DISCOUNT_REVIEW_PERCENT=15

# --- 自动维护总开关（两个都必须为 true 才会外发源码与意见）---
MAINTENANCE_ENABLED=false
ALLOW_CODE_EXTERNAL=false
# 双机模式：构建/测试在新加坡，运行在本机容器
MAINT_DEPLOY_TARGET=docker-split
MAINT_AUTO_PUBLISH=true
MAINT_RUNTIME_DIR=/opt/huakangos/data/maintenance
MAINT_APP_DATA_DIR=/opt/huakangos/data
MAINT_APP_CONTAINER=huakangos-app
MAINT_APP_IMAGE_PREFIX=huakangos-app
MAINT_APP_PUBLISH_HOST=127.0.0.1
MAINT_APP_PUBLISH_PORT=8000
MAINT_APP_PORT=8000
# 这台机器只有 1.6GB 内存：容器限额必须保守
MAINT_APP_MEMORY=512m
MAINT_APP_CPUS=1
# MAINT_TEST_IMAGE 在双机模式下不在本机使用：隔离测试镜像只存在于构建机，
# 由构建机的 HKB_TEST_IMAGE 指定。
MAINT_TEST_IMAGE=dealerdesk-tests:0.2
MAINT_MAX_JOBS_PER_DAY=3
MAINT_APPROVAL_HOURS=24

# --- 维护窗口与让行（时区显式指定，与本机 / 构建机的系统时区无关）---
MAINT_WINDOW_TZ=Asia/Shanghai
MAINT_WINDOW_START=22:00
MAINT_WINDOW_END=06:00
# 量化交易保护区间：构建机上的量化任务每 4 小时一次，00:01 / 04:01 前后让行
MAINT_WINDOW_BANS=23:50-00:30,03:50-04:30
MAINT_MIN_SEGMENT_MINUTES=20
MAINT_SLOT_ATTEMPTS=10
MAINT_SLOT_PAUSE_SECONDS=60
# 本机（阿里云）没有量化 systemd 单元，留空即可；填了但 systemctl 不可用会按“让行”处理
MAINT_QUANT_UNITS=

# --- 构建机（新加坡）连接信息 ---
# 必填：构建机地址与用户名（用户名必须是构建机上那个受限用户，install.sh 默认 hkbuild）
MAINT_SG_HOST=207.148.126.193
MAINT_SG_USER=hkbuild
# 必填：控制器私钥路径（只读、0600、属主 huakang）
MAINT_SG_KEY=/opt/huakangos/.ssh/sg_builder_ed25519
MAINT_SG_PORT=22
MAINT_SG_TIMEOUT=900

# --- 代码仓库（只用于审批卡片里的 compare 链接与基线名）---
MAINT_REPO_WEB_URL=
MAINT_BASE_BRANCH=main
# 双机模式下控制器不克隆仓库（克隆与推送都在构建机），可留空
MAINT_REPO_URL=

# --- DeepSeek 编码接口（可复用上面的密钥与模型）---
DEEPSEEK_CODE_API_KEY=
DEEPSEEK_CODE_MODEL=

# --- 飞书应用机器人（自建应用，不是自定义 webhook）---
FEISHU_APP_ID=
FEISHU_APP_SECRET=
# 必填：审批人在**该应用下**的 open_id（ou_ 开头），多个用英文逗号分隔
FEISHU_APPROVER_OPEN_IDS=
FEISHU_RECEIVE_ID_TYPE=open_id
FEISHU_RECEIVE_ID=
# 选填：填错会阻止所有审批
FEISHU_TENANT_KEY=
ENVEOF
  chown root:"${CONTAINER_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  info "已生成 ${ENV_FILE} 模板（0640，root:${CONTAINER_GROUP}）：值全部为空，密钥请人工填写"
fi

# -----------------------------------------------------------------------------
# 5. 控制器 venv 与依赖
# -----------------------------------------------------------------------------
info '步骤 5/7：准备控制器 Python 环境'
[[ -f "${CONTROLLER_DIR}/requirements-maintenance.txt" ]] || die "缺少 ${CONTROLLER_DIR}/requirements-maintenance.txt。
请先把本项目（人工审阅过的可信版本）放到 ${CONTROLLER_DIR}，例如在本地执行：
    rsync -a --exclude .venv --exclude data --exclude .git ./ root@8.133.192.159:${CONTROLLER_DIR}/
或在该目录内 git clone 专用仓库后 checkout 到指定提交，然后重新运行本脚本。"

PYTHON_BIN=''
# 优先用已安装的 3.13/3.12/3.11（项目支持 3.11-3.13）；都没有时退回系统 python3
# ——Ubuntu 22.04 上是 3.10，项目不支持，下面的版本闸门会让本脚本以非零码退出。
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "${candidate}" >/dev/null 2>&1; then PYTHON_BIN="$(command -v "${candidate}")"; break; fi
done
[[ -n "${PYTHON_BIN}" ]] || die '找不到 python3：请先 apt-get install -y python3 python3-venv python3-pip'

py_version() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true; }
PY_VERSION="$(py_version "${PYTHON_BIN}")"
info "使用 ${PYTHON_BIN}（Python ${PY_VERSION}）"

if [[ -x "${VENV_DIR}/bin/python" ]]; then
  existing_version="$(py_version "${VENV_DIR}/bin/python")"
  case "${existing_version}" in
    3.11|3.12|3.13) info "复用已有 venv（Python ${existing_version}）" ;;
    *) warn "已有 venv 的解释器是 Python ${existing_version}，不受支持：删除后重建"
       rm -rf -- "${VENV_DIR}" ;;
  esac
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
    warn "创建 venv 失败：可能缺少与 ${PYTHON_BIN} 匹配的 venv 包（如 python3.12-venv）。"
    die "请安装 python3.12 与 python3.12-venv 后重新运行本脚本（本脚本会自动优先使用 3.12）"
  fi
  info "已创建 venv：${VENV_DIR}"
fi

PIP_FAILED=0
"${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || warn 'pip 自升级失败，继续尝试安装依赖'
"${VENV_DIR}/bin/python" -m pip install --upgrade --requirement "${CONTROLLER_DIR}/requirements-maintenance.txt" || PIP_FAILED=1

if [[ "${PIP_FAILED}" -ne 0 ]]; then
  warn '依赖安装失败。请检查上面的 pip 报错（网络、apt 镜像或版本解析）。'
  cat >&2 <<'PYFIX'
【处理办法】安装 Python 3.12 后重新运行本脚本（脚本会自动优先使用 3.12）：
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get install -y python3.12 python3.12-venv
若本机无法访问 deadsnakes，请自行编译或从官方源安装 Python 3.12（同样放到 /usr/bin/python3.12）。
本脚本不会静默继续：让控制器跑在不受支持的解释器上，会在真正发布时以更难排查的方式失败。
PYFIX
  exit 1
fi

# 实测（2026-09-19，阿里云 8.133.192.159）：Ubuntu 22.04 自带的 Python 3.10.12 可以完整安装并
# 导入 requirements-maintenance.txt 的全部固定版本依赖，代码也没有 3.11+ 专属语法。所以这里不再
# 因为「解释器不是 3.11-3.13」就拒绝安装——真正的判据是下面那段导入自检。
case "${PY_VERSION}" in
  3.10|3.11|3.12|3.13)
    info "控制器依赖安装完成（Python ${PY_VERSION}）" ;;
  *)
    warn "当前解释器是 Python ${PY_VERSION}，超出实测范围（3.10-3.13）。继续执行导入自检；自检失败会以非零码退出。"
    ;;
esac

# 装上了不等于跑得起来：真正导入控制器与业务模块（不连数据库、不联网、不发消息）。
if ! ( cd "${CONTROLLER_DIR}" && "${VENV_DIR}/bin/python" -c 'import app.config, app.db, maintenance.supervisor, lark_oapi' ); then
  die '控制器依赖自检失败：请按上面的 Python 3.12 说明处理后再重新运行本脚本（本脚本不会把半成品当成安装成功）'
fi
info '控制器依赖自检通过（app.config / app.db / maintenance.supervisor / lark_oapi 均可导入）'

# -----------------------------------------------------------------------------
# 6. 安装 systemd 单元（不 enable / 不 start）
# -----------------------------------------------------------------------------
info '步骤 6/7：安装 systemd 单元'
[[ -f "${UNIT_SRC}" ]] || die "找不到 ${UNIT_SRC}：请连同 deploy/aliyun/huakangos-controller.service 一起上传"
install -m 0644 -o root -g root "${UNIT_SRC}" "${UNIT_PATH}"
systemctl daemon-reload
chown -R "${APP_USER}:${CONTAINER_GROUP}" "${CONTROLLER_DIR}" 2>/dev/null || true
info "已安装 ${UNIT_PATH} 并执行 daemon-reload（刻意没有 enable/start）"

# -----------------------------------------------------------------------------
# 7. 后续步骤
# -----------------------------------------------------------------------------
cat <<'NEXT'

================================================================================
安装完成。以下步骤必须由人工完成（本脚本不写密钥、不启服务）：
================================================================================
1) 填写 /etc/huakangos/huakangos.env（模板已生成，0640）。必须填的：
     ALLOWED_HOSTS                    业务对外域名/IP（不能含 * 或 testserver）
     DEEPSEEK_API_KEY                 业务 AI（不用可留空，ALLOW_AI_EXTERNAL 保持 false）
     MAINT_REPO_WEB_URL               https 的仓库页面，用来生成 compare 链接
     MAINT_SG_HOST / MAINT_SG_USER    构建机地址与受限用户名
     MAINT_SG_KEY                     控制器私钥路径（下一步生成）
     FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_APPROVER_OPEN_IDS / FEISHU_RECEIVE_ID
     MAINTENANCE_ENABLED=true 且 ALLOW_CODE_EXTERNAL=true（确认愿意外发白名单源码后再开）
   改完执行：chown root:<容器组> /etc/huakangos/huakangos.env && chmod 0640 同路径

2) 生成本机到构建机的专用密钥（命令只在阿里云执行，私钥永不离开本机）：
     sudo -u huakang ssh-keygen -t ed25519 -a 100 -N '' \
       -C 'huakangos-controller@8.133.192.159' \
       -f /opt/huakangos/.ssh/sg_builder_ed25519
   然后把 /opt/huakangos/.ssh/sg_builder_ed25519.pub 的内容追加到构建机上
   /opt/huakangos-builder/.ssh/authorized_keys（见 deploy/sg/authorized_keys.snippet）。

3) 预置构建机主机密钥（控制器用 StrictHostKeyChecking=yes，不做 TOFU）：
   把构建机 install.sh 打印的 ssh_host_ed25519_key.pub 一行写进
   /opt/huakangos/.ssh/known_hosts（格式：207.148.126.193 ssh-ed25519 AAAA...），
   或临时用 ssh-keyscan -t ed25519 207.148.126.193 并人工核对指纹。

4) 初始化业务数据库（必须用 huakang 身份，否则库文件属主会变成 root）：
     sudo -u huakang env -i HOME=/opt/huakangos PATH=/usr/bin:/bin \
       bash -c 'set -a; . /etc/huakangos/huakangos.env; set +a; \
                cd /opt/huakangos/controller && .venv/bin/python -m app.cli init'

5) 接好维护依赖后自检（不会调用 DeepSeek、不会发送审批卡片、不会发布）：
     sudo -u huakang bash -c 'set -a; . /etc/huakangos/huakangos.env; set +a; \
       cd /opt/huakangos/controller && .venv/bin/python -m maintenance.doctor'

6) 启动控制器（它会自行拉起业务容器；反向代理请指向 127.0.0.1:8000）：
     systemctl enable --now huakangos-controller
     journalctl -u huakangos-controller -f
================================================================================
NEXT

info "上面提到的「容器组」就是 ${CONTAINER_GROUP}（GID ${CONTAINER_UID}，与容器内用户 10001:10001 对齐）"
info '全部步骤完成；服务尚未启动，请按上面的清单继续'